//! Gerenciador multiagente (etapa 0.5).
//!
//! Vários "papéis" (planejador, programador, pesquisador, crítico,
//! executor) compartilham um único modelo carregado no `llama-server`
//! (ver ia-server) em vez de um modelo por agente — ver
//! docs/architecture.md. `AgentManager` mantém uma fila de tarefas e um
//! único worker thread que as processa sequencialmente contra
//! `llama_client::complete`, refletindo a decisão de projeto de que, em
//! hardware modesto, os agentes trabalham de forma cooperativa/
//! sequencial, não em paralelo.

use std::collections::HashMap;
use std::fmt;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use std::thread;

use crate::llama_client;

const DEFAULT_N_PREDICT: u32 = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentRole {
    Planejador,
    Programador,
    Pesquisador,
    Critico,
    Executor,
}

impl AgentRole {
    pub fn label(&self) -> &'static str {
        match self {
            AgentRole::Planejador => "planejador",
            AgentRole::Programador => "programador",
            AgentRole::Pesquisador => "pesquisador",
            AgentRole::Critico => "critico",
            AgentRole::Executor => "executor",
        }
    }

    pub fn parse(s: &str) -> Option<AgentRole> {
        match s.trim().to_ascii_lowercase().as_str() {
            "planejador" => Some(AgentRole::Planejador),
            "programador" => Some(AgentRole::Programador),
            "pesquisador" => Some(AgentRole::Pesquisador),
            "critico" | "crítico" => Some(AgentRole::Critico),
            "executor" => Some(AgentRole::Executor),
            _ => None,
        }
    }
}

impl fmt::Display for AgentRole {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.label())
    }
}

pub const PLANNED_ROLES: [AgentRole; 5] = [
    AgentRole::Planejador,
    AgentRole::Programador,
    AgentRole::Pesquisador,
    AgentRole::Critico,
    AgentRole::Executor,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskStatus {
    Queued,
    Running,
    Done,
    Error,
}

impl fmt::Display for TaskStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            TaskStatus::Queued => "queued",
            TaskStatus::Running => "running",
            TaskStatus::Done => "done",
            TaskStatus::Error => "error",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone)]
pub struct Task {
    pub id: u64,
    pub role: AgentRole,
    pub prompt: String,
    pub status: TaskStatus,
    /// Resultado (quando `status == Done`) ou mensagem de erro (quando
    /// `status == Error`).
    pub result: Option<String>,
    /// Tokens/s reportados pelo llama-server para esta tarefa (etapa
    /// 0.8, telemetria real — ver `llama_client::CompletionResult`).
    /// `None` em tarefas com erro ou quando o servidor não reportou.
    pub tokens_per_second: Option<f64>,
}

/// Fila de tarefas + worker único, compartilhando um endereço de
/// `llama-server`. `submit` nunca bloqueia: apenas enfileira e retorna o
/// id da tarefa; o chamador consulta o resultado depois com `status`.
pub struct AgentManager {
    tasks: Mutex<HashMap<u64, Task>>,
    order: Mutex<Vec<u64>>,
    next_id: AtomicU64,
    sender: Sender<u64>,
}

impl AgentManager {
    pub fn spawn(llama_addr: String) -> Arc<AgentManager> {
        let (tx, rx) = mpsc::channel::<u64>();
        let manager = Arc::new(AgentManager {
            tasks: Mutex::new(HashMap::new()),
            order: Mutex::new(Vec::new()),
            next_id: AtomicU64::new(1),
            sender: tx,
        });

        let worker_manager = Arc::clone(&manager);
        thread::spawn(move || worker_loop(rx, worker_manager, llama_addr));

        manager
    }

    pub fn submit(&self, role: AgentRole, prompt: String) -> u64 {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let task = Task {
            id,
            role,
            prompt,
            status: TaskStatus::Queued,
            result: None,
            tokens_per_second: None,
        };
        self.tasks.lock().unwrap().insert(id, task);
        self.order.lock().unwrap().push(id);
        // Se o worker já saiu (não deveria acontecer em produção — o
        // processo inteiro cairia junto), a tarefa simplesmente fica
        // Queued para sempre; STATUS continua reportando isso com
        // honestidade em vez de travar o chamador.
        let _ = self.sender.send(id);
        id
    }

    pub fn status(&self, id: u64) -> Option<Task> {
        self.tasks.lock().unwrap().get(&id).cloned()
    }

    pub fn list(&self) -> Vec<Task> {
        let order = self.order.lock().unwrap();
        let tasks = self.tasks.lock().unwrap();
        order
            .iter()
            .filter_map(|id| tasks.get(id).cloned())
            .collect()
    }

    pub fn summary(&self) -> (usize, usize, usize, usize) {
        let tasks = self.tasks.lock().unwrap();
        let mut queued = 0;
        let mut running = 0;
        let mut done = 0;
        let mut error = 0;
        for task in tasks.values() {
            match task.status {
                TaskStatus::Queued => queued += 1,
                TaskStatus::Running => running += 1,
                TaskStatus::Done => done += 1,
                TaskStatus::Error => error += 1,
            }
        }
        (queued, running, done, error)
    }

    /// Telemetria de throughput para `telemetry::adapt_weight` (etapa
    /// 0.8): média das últimas `recent_n` tarefas `Done` com tokens/s
    /// registrado (mais recentes primeiro) e o melhor valor já
    /// observado entre TODAS as tarefas concluídas nesta sessão do
    /// daemon (não persiste — reinicia quando `ai-core` reinicia).
    /// `(None, None)` enquanto nenhuma tarefa com tokens/s tiver
    /// concluído ainda.
    pub fn tokens_per_second_stats(&self, recent_n: usize) -> (Option<f64>, Option<f64>) {
        let order = self.order.lock().unwrap();
        let tasks = self.tasks.lock().unwrap();

        let mut samples_recent_first: Vec<f64> = order
            .iter()
            .rev()
            .filter_map(|id| tasks.get(id))
            .filter(|t| t.status == TaskStatus::Done)
            .filter_map(|t| t.tokens_per_second)
            .collect();

        let best = samples_recent_first
            .iter()
            .copied()
            .fold(None, |acc: Option<f64>, v| {
                Some(acc.map_or(v, |a| a.max(v)))
            });

        samples_recent_first.truncate(recent_n);
        let recent_avg = if samples_recent_first.is_empty() {
            None
        } else {
            Some(samples_recent_first.iter().sum::<f64>() / samples_recent_first.len() as f64)
        };

        (recent_avg, best)
    }
}

fn worker_loop(rx: mpsc::Receiver<u64>, manager: Arc<AgentManager>, llama_addr: String) {
    for id in rx {
        let prompt = {
            let mut tasks = manager.tasks.lock().unwrap();
            match tasks.get_mut(&id) {
                Some(task) => {
                    task.status = TaskStatus::Running;
                    task.prompt.clone()
                }
                None => continue,
            }
        };

        let outcome = llama_client::complete(&llama_addr, &prompt, DEFAULT_N_PREDICT);

        let mut tasks = manager.tasks.lock().unwrap();
        if let Some(task) = tasks.get_mut(&id) {
            match outcome {
                Ok(completion) => {
                    task.status = TaskStatus::Done;
                    task.result = Some(completion.content);
                    task.tokens_per_second = completion.tokens_per_second;
                }
                Err(e) => {
                    task.status = TaskStatus::Error;
                    task.result = Some(e);
                }
            }
        }
    }
}

pub fn status_line(manager: &AgentManager) -> String {
    let (queued, running, done, error) = manager.summary();
    format!(
        "multiagente: {} tarefas (fila={queued} executando={running} concluidas={done} erro={error}) — papeis: {}",
        queued + running + done + error,
        PLANNED_ROLES.iter().map(|r| r.label()).collect::<Vec<_>>().join(", ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, Write};
    use std::net::TcpListener;
    use std::thread;
    use std::time::{Duration, Instant};

    fn spawn_mock_llama_server(response_content: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap().to_string();

        thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { continue };
                let mut reader = std::io::BufReader::new(stream.try_clone().unwrap());
                let mut line = String::new();
                let _ = reader.read_line(&mut line);
                let body = format!("{{\"content\":\"{response_content}\"}}");
                let response = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                    body.len()
                );
                let _ = stream.write_all(response.as_bytes());
            }
        });

        addr
    }

    /// Como `spawn_mock_llama_server`, mas cada conexão consecutiva
    /// recebe o próximo valor de `tokens_per_second` de `values` (em
    /// ordem — o worker do `AgentManager` processa uma tarefa por vez,
    /// então a ordem de conexão bate com a ordem de `submit`).
    fn spawn_mock_llama_server_with_varying_tps(values: Vec<f64>) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap().to_string();

        thread::spawn(move || {
            let mut values = values.into_iter();
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { continue };
                let mut reader = std::io::BufReader::new(stream.try_clone().unwrap());
                let mut line = String::new();
                let _ = reader.read_line(&mut line);
                let tps = values.next().unwrap_or(0.0);
                let body = format!(
                    "{{\"content\":\"ok\",\"timings\":{{\"predicted_per_second\":{tps}}}}}"
                );
                let response = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                    body.len()
                );
                let _ = stream.write_all(response.as_bytes());
            }
        });

        addr
    }

    fn wait_until<F: Fn() -> bool>(timeout: Duration, check: F) -> bool {
        let start = Instant::now();
        while start.elapsed() < timeout {
            if check() {
                return true;
            }
            thread::sleep(Duration::from_millis(10));
        }
        false
    }

    fn wait_for_completion(manager: &AgentManager, id: u64) {
        let completed = wait_until(Duration::from_secs(5), || {
            matches!(
                manager.status(id).map(|t| t.status),
                Some(TaskStatus::Done) | Some(TaskStatus::Error)
            )
        });
        assert!(completed, "tarefa {id} não terminou a tempo");
    }

    #[test]
    fn role_label_and_parse_roundtrip() {
        for role in PLANNED_ROLES {
            assert_eq!(AgentRole::parse(role.label()), Some(role));
        }
        assert_eq!(AgentRole::parse("PLANEJADOR"), Some(AgentRole::Planejador));
        assert_eq!(AgentRole::parse("inexistente"), None);
    }

    #[test]
    fn submit_and_complete_task_against_mock_server() {
        let addr = spawn_mock_llama_server("resposta simulada");
        let manager = AgentManager::spawn(addr);

        let id = manager.submit(AgentRole::Pesquisador, "pesquise algo".to_string());

        let completed = wait_until(Duration::from_secs(5), || {
            matches!(
                manager.status(id).map(|t| t.status),
                Some(TaskStatus::Done) | Some(TaskStatus::Error)
            )
        });
        assert!(completed, "tarefa não terminou a tempo");

        let task = manager.status(id).unwrap();
        assert_eq!(task.status, TaskStatus::Done);
        assert_eq!(task.result.as_deref(), Some("resposta simulada"));
        assert_eq!(task.role, AgentRole::Pesquisador);
    }

    #[test]
    fn status_for_unknown_id_is_none() {
        let manager = AgentManager::spawn("127.0.0.1:1".to_string());
        assert!(manager.status(9999).is_none());
    }

    #[test]
    fn failed_backend_marks_task_as_error() {
        // porta sem servidor nenhum escutando
        let manager = AgentManager::spawn("127.0.0.1:1".to_string());
        let id = manager.submit(AgentRole::Executor, "faca algo".to_string());

        let completed = wait_until(Duration::from_secs(10), || {
            matches!(
                manager.status(id).map(|t| t.status),
                Some(TaskStatus::Done) | Some(TaskStatus::Error)
            )
        });
        assert!(completed, "tarefa não terminou a tempo");
        assert_eq!(manager.status(id).unwrap().status, TaskStatus::Error);
    }

    #[test]
    fn list_preserves_submission_order() {
        let manager = AgentManager::spawn("127.0.0.1:1".to_string());
        let id1 = manager.submit(AgentRole::Planejador, "a".to_string());
        let id2 = manager.submit(AgentRole::Programador, "b".to_string());
        let id3 = manager.submit(AgentRole::Critico, "c".to_string());

        let ids: Vec<u64> = manager.list().iter().map(|t| t.id).collect();
        assert_eq!(ids, vec![id1, id2, id3]);
    }

    #[test]
    fn status_line_reports_role_labels() {
        let manager = AgentManager::spawn("127.0.0.1:1".to_string());
        let line = status_line(&manager);
        for role in PLANNED_ROLES {
            assert!(line.contains(role.label()));
        }
    }

    #[test]
    fn completed_task_records_tokens_per_second() {
        let addr = spawn_mock_llama_server_with_varying_tps(vec![42.5]);
        let manager = AgentManager::spawn(addr);

        let id = manager.submit(AgentRole::Executor, "faca algo".to_string());
        wait_for_completion(&manager, id);

        let task = manager.status(id).unwrap();
        assert_eq!(task.status, TaskStatus::Done);
        assert_eq!(task.tokens_per_second, Some(42.5));
    }

    #[test]
    fn tokens_per_second_stats_before_any_completion_is_none() {
        let manager = AgentManager::spawn("127.0.0.1:1".to_string());
        assert_eq!(manager.tokens_per_second_stats(3), (None, None));
    }

    #[test]
    fn tokens_per_second_stats_tracks_recent_average_and_session_best() {
        let addr = spawn_mock_llama_server_with_varying_tps(vec![10.0, 30.0, 20.0]);
        let manager = AgentManager::spawn(addr);

        let id1 = manager.submit(AgentRole::Executor, "a".to_string());
        wait_for_completion(&manager, id1);
        let id2 = manager.submit(AgentRole::Executor, "b".to_string());
        wait_for_completion(&manager, id2);
        let id3 = manager.submit(AgentRole::Executor, "c".to_string());
        wait_for_completion(&manager, id3);

        // últimas 2 tarefas (mais recentes primeiro): id3=20.0, id2=30.0 -> média 25.0
        let (recent_avg, best) = manager.tokens_per_second_stats(2);
        assert_eq!(recent_avg, Some(25.0));
        // melhor entre TODAS as 3 (10.0, 30.0, 20.0), não só as 2 recentes
        assert_eq!(best, Some(30.0));
    }

    #[test]
    fn tokens_per_second_stats_ignores_failed_tasks() {
        // servidor de mentira encerrado: toda tarefa termina em erro, sem tokens/s
        let manager = AgentManager::spawn("127.0.0.1:1".to_string());
        let id = manager.submit(AgentRole::Executor, "falha".to_string());
        wait_for_completion(&manager, id);

        assert_eq!(manager.status(id).unwrap().status, TaskStatus::Error);
        assert_eq!(manager.tokens_per_second_stats(5), (None, None));
    }
}
