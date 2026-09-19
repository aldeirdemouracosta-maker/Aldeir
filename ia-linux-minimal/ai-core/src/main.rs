//! ai-core — daemon central do IA Linux Minimal.
//!
//! Detecta hardware, gerencia modelos GGUF e o backend de inferência
//! (CPU/Vulkan), e expõe tudo isso via socket Unix para o `ia-shell` e
//! outros clientes locais. Ver docs/architecture.md.

mod agent;
mod backend;
mod config;
mod hardware;
mod ipc;
mod json;
mod llama_client;
mod memory;
mod model;

use std::env;
use std::path::PathBuf;
use std::process;
use std::sync::{Arc, Mutex};

use agent::AgentManager;
use backend::{BackendMode, ResolvedBackend};
use hardware::HardwareInfo;

const VERSION: &str = env!("CARGO_PKG_VERSION");
const DEFAULT_SOCKET: &str = "/run/ia-core.sock";
const DEFAULT_DATA_DIR: &str = "/data";
// Mesmo endereço padrão que `ia-server start` usa para o llama-server
// (ver rootfs-overlay/usr/bin/ia-server) — ai-core não inicia o
// llama-server sozinho, apenas fala com ele quando uma tarefa é
// submetida (ver agent.rs).
const DEFAULT_LLAMA_ADDR: &str = "127.0.0.1:8080";
// Mesmo diretório que ia-server usa para o PID file (/run/ia-server.pid)
// — ai-core lê esse PID para saber o que proteger via cgroup (memory.rs).
const DEFAULT_RUN_DIR: &str = "/run";

pub struct State {
    data_dir: PathBuf,
    hardware: HardwareInfo,
    backend_mode: Mutex<BackendMode>,
    agent_manager: Arc<AgentManager>,
    damon_dir: PathBuf,
    cgroup_root: PathBuf,
    run_dir: PathBuf,
}

fn main() {
    // Um único binário atua como servidor (sem argumentos — é assim que
    // inittab o inicia) e como cliente (com argumentos — é assim que
    // ia-shell, ia-model, ia-chat etc. falam com o daemon). Isso evita
    // depender de suporte a socket Unix em `busybox nc`, que não é
    // garantido em todas as configurações do BusyBox.
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        run_server();
    } else {
        run_client(&args);
    }
}

fn run_client(args: &[String]) {
    let socket_path = env::var("IA_CORE_SOCKET").unwrap_or_else(|_| DEFAULT_SOCKET.to_string());
    let command_line = args.join(" ");

    match ipc::query(&socket_path, &command_line) {
        Ok(lines) => {
            let mut had_error = false;
            for line in lines {
                if line.starts_with("ERRO") {
                    eprintln!("{line}");
                    had_error = true;
                } else {
                    println!("{line}");
                }
            }
            if had_error {
                process::exit(1);
            }
        }
        Err(e) => {
            eprintln!("ai-core: não foi possível contatar o daemon ({socket_path}): {e}");
            process::exit(2);
        }
    }
}

fn run_server() {
    let data_dir =
        PathBuf::from(env::var("IA_DATA_DIR").unwrap_or_else(|_| DEFAULT_DATA_DIR.to_string()));
    let socket_path = env::var("IA_CORE_SOCKET").unwrap_or_else(|_| DEFAULT_SOCKET.to_string());

    let hw = hardware::detect();
    let backend_mode = config::load_backend_mode(&data_dir);
    let llama_addr = env::var("IA_LLAMA_ADDR").unwrap_or_else(|_| DEFAULT_LLAMA_ADDR.to_string());
    let damon_dir = PathBuf::from(
        env::var("IA_DAMON_SYSFS")
            .unwrap_or_else(|_| memory::DEFAULT_DAMON_RECLAIM_DIR.to_string()),
    );
    let cgroup_root = PathBuf::from(
        env::var("IA_CGROUP_ROOT").unwrap_or_else(|_| memory::DEFAULT_CGROUP_ROOT.to_string()),
    );
    let run_dir =
        PathBuf::from(env::var("IA_RUN_DIR").unwrap_or_else(|_| DEFAULT_RUN_DIR.to_string()));

    eprintln!(
        "ai-core {VERSION}: CPU='{}' threads={} RAM={:.1}GiB perfil={} GPU={}",
        hw.cpu_model,
        hw.cpu_threads,
        hw.ram_total_gb(),
        hw.profile().label(),
        hw.gpu
            .as_ref()
            .map(|g| g.driver.as_str())
            .unwrap_or("nenhuma")
    );

    let agent_manager = AgentManager::spawn(llama_addr);

    let state = Arc::new(State {
        data_dir,
        hardware: hw,
        backend_mode: Mutex::new(backend_mode),
        agent_manager,
        damon_dir,
        cgroup_root,
        run_dir,
    });

    if let Err(e) = ipc::serve(&socket_path, state, dispatch) {
        eprintln!("ai-core: erro fatal no servidor IPC ({socket_path}): {e}");
        process::exit(1);
    }
}

fn dispatch(line: &str, state: &State) -> Vec<String> {
    let line = line.trim();
    let mut parts = line.split_whitespace();
    let cmd = parts.next().unwrap_or("").to_ascii_uppercase();
    let rest: Vec<&str> = parts.collect();

    match cmd.as_str() {
        "PING" => vec!["PONG".to_string()],
        "VERSION" => vec![format!("ai-core {VERSION}")],
        "STATUS" => status_lines(state),
        "HW" => hw_lines(state),
        "MODEL" => model_dispatch(&rest, state),
        "BACKEND" => backend_dispatch(&rest, state),
        "AGENT" => agent_dispatch(&rest, state),
        "MEMORY" => memory_dispatch(&rest, state),
        "" => vec!["ERRO comando vazio".to_string()],
        other => vec![format!("ERRO comando desconhecido: {other}")],
    }
}

fn status_lines(state: &State) -> Vec<String> {
    let hw = &state.hardware;
    let mode = *state.backend_mode.lock().unwrap();
    let resolved = backend::resolve(mode, hw);
    let active = model::active_model(&state.data_dir).unwrap_or_else(|| "nenhum".to_string());
    let model_count = model::list_models(&state.data_dir).len();

    vec![
        format!("versao={VERSION}"),
        format!("cpu={}", hw.cpu_model),
        format!("threads={}", hw.cpu_threads),
        format!("ram_gb={:.1}", hw.ram_total_gb()),
        format!("perfil={}", hw.profile().label()),
        format!(
            "gpu={}",
            hw.gpu
                .as_ref()
                .map(|g| g.driver.as_str())
                .unwrap_or("nenhuma")
        ),
        format!("backend_modo={mode}"),
        format!("backend_resolvido={resolved}"),
        format!("modelos_disponiveis={model_count}"),
        format!("modelo_ativo={active}"),
        agent::status_line(&state.agent_manager),
        format!(
            "memoria_damon={}",
            if memory::read_status(&state.damon_dir).is_some() {
                "disponivel"
            } else {
                "indisponivel"
            }
        ),
        format!(
            "memoria_protegida={}",
            memory::read_protection_status(&state.cgroup_root).is_some()
        ),
    ]
}

fn hw_lines(state: &State) -> Vec<String> {
    let hw = &state.hardware;
    // /data/config/runtime.conf permite ao usuário sobrepor os valores
    // calculados automaticamente (ex.: CPU sem AVX2 pode preferir menos
    // threads do que hw.suggested_threads() sugere).
    let overrides = config::load_runtime_conf(&state.data_dir);
    let threads = overrides
        .get("IA_THREADS")
        .cloned()
        .unwrap_or_else(|| hw.suggested_threads().to_string());
    let ctx = overrides
        .get("IA_CTX")
        .cloned()
        .unwrap_or_else(|| hw.profile().suggested_ctx().to_string());
    let batch = overrides
        .get("IA_BATCH")
        .cloned()
        .unwrap_or_else(|| "256".to_string());

    vec![
        format!("cpu_model={}", hw.cpu_model),
        format!("cpu_threads={}", hw.cpu_threads),
        format!("threads_sugeridas={}", hw.suggested_threads()),
        format!("threads_efetivas={threads}"),
        format!("ram_total_kb={}", hw.ram_total_kb),
        format!("perfil={}", hw.profile().label()),
        format!("contexto_sugerido={}", hw.profile().suggested_ctx()),
        format!("contexto_efetivo={ctx}"),
        format!("batch_efetivo={batch}"),
        match &hw.gpu {
            Some(g) => format!("gpu_driver={} gpu_render_node={}", g.driver, g.render_node),
            None => "gpu=nenhuma".to_string(),
        },
    ]
}

fn model_dispatch(rest: &[&str], state: &State) -> Vec<String> {
    match rest.first() {
        Some(&"LIST") | None => {
            let models = model::list_models(&state.data_dir);
            if models.is_empty() {
                vec!["nenhum modelo em /data/models".to_string()]
            } else {
                models
                    .iter()
                    .enumerate()
                    .map(|(i, m)| {
                        format!(
                            "{}) {} ({:.0} MB)",
                            i + 1,
                            m.name,
                            m.size_bytes as f64 / 1024.0 / 1024.0
                        )
                    })
                    .collect()
            }
        }
        Some(&"ACTIVE") => {
            vec![model::active_model(&state.data_dir)
                .unwrap_or_else(|| "nenhum modelo ativo".to_string())]
        }
        Some(&"SELECT") => match rest.get(1).and_then(|s| s.parse::<usize>().ok()) {
            Some(idx) => match model::set_active_by_index(&state.data_dir, idx) {
                Ok(name) => vec![format!("modelo ativo definido: {name}")],
                Err(e) => vec![format!("ERRO {e}")],
            },
            None => vec!["ERRO uso: MODEL SELECT <indice>".to_string()],
        },
        Some(&"RECOMMEND") => vec![model::recommend(state.hardware.profile()).to_string()],
        Some(other) => vec![format!("ERRO subcomando MODEL desconhecido: {other}")],
    }
}

fn backend_dispatch(rest: &[&str], state: &State) -> Vec<String> {
    match rest.first() {
        Some(&"GET") | None => {
            let mode = *state.backend_mode.lock().unwrap();
            let resolved = backend::resolve(mode, &state.hardware);
            vec![format!("modo={mode} resolvido={resolved}")]
        }
        Some(&"SET") => match rest.get(1).and_then(|s| BackendMode::parse(s)) {
            Some(new_mode) => {
                *state.backend_mode.lock().unwrap() = new_mode;
                match config::save_backend_mode(&state.data_dir, new_mode) {
                    Ok(()) => {
                        let resolved: ResolvedBackend = backend::resolve(new_mode, &state.hardware);
                        vec![format!(
                            "backend definido: modo={new_mode} resolvido={resolved}"
                        )]
                    }
                    Err(e) => vec![format!("ERRO {e}")],
                }
            }
            None => vec!["ERRO uso: BACKEND SET <auto|cpu|vulkan>".to_string()],
        },
        Some(other) => vec![format!("ERRO subcomando BACKEND desconhecido: {other}")],
    }
}

fn agent_dispatch(rest: &[&str], state: &State) -> Vec<String> {
    match rest.first() {
        Some(&"ROLES") => agent::PLANNED_ROLES
            .iter()
            .enumerate()
            .map(|(i, r)| format!("{}) {}", i + 1, r.label()))
            .collect(),
        Some(&"TASK") => {
            let role = match rest.get(1).and_then(|s| agent::AgentRole::parse(s)) {
                Some(r) => r,
                None => return vec!["ERRO uso: AGENT TASK <papel> <texto da tarefa>".to_string()],
            };
            let prompt = rest[2..].join(" ");
            if prompt.is_empty() {
                return vec!["ERRO uso: AGENT TASK <papel> <texto da tarefa>".to_string()];
            }
            let id = state.agent_manager.submit(role, prompt);
            vec![format!("tarefa {id} enfileirada (papel={role})")]
        }
        Some(&"STATUS") => match rest.get(1).and_then(|s| s.parse::<u64>().ok()) {
            Some(id) => match state.agent_manager.status(id) {
                Some(task) => {
                    let mut lines = vec![format!(
                        "id={} papel={} status={}",
                        task.id, task.role, task.status
                    )];
                    if let Some(result) = task.result {
                        lines.push(result);
                    }
                    lines
                }
                None => vec![format!("ERRO tarefa não encontrada: {id}")],
            },
            None => vec!["ERRO uso: AGENT STATUS <id>".to_string()],
        },
        Some(&"LIST") | None => {
            let tasks = state.agent_manager.list();
            if tasks.is_empty() {
                vec!["nenhuma tarefa enfileirada ainda".to_string()]
            } else {
                tasks
                    .iter()
                    .map(|t| {
                        let preview: String = t.prompt.chars().take(40).collect();
                        format!(
                            "{}) papel={} status={} tarefa=\"{preview}\"",
                            t.id, t.role, t.status
                        )
                    })
                    .collect()
            }
        }
        Some(other) => vec![format!("ERRO subcomando AGENT desconhecido: {other}")],
    }
}

fn memory_dispatch(rest: &[&str], state: &State) -> Vec<String> {
    match rest.first() {
        Some(&"STATUS") | None => {
            let mut lines = match memory::read_status(&state.damon_dir) {
                Some(p) => vec![format!(
                    "damon_reclaim: enabled={} min_age_ms={} quota_ms={} quota_sz_bytes={}",
                    p.enabled, p.min_age_ms, p.quota_ms, p.quota_sz_bytes
                )],
                None => vec!["damon_reclaim: indisponivel neste kernel (modulo nao carregado ou nao suportado)".to_string()],
            };
            match memory::read_protection_status(&state.cgroup_root) {
                Some((low, procs)) => {
                    lines.push(format!("cgroup: memory.low={low} bytes pids={:?}", procs))
                }
                None => lines.push("cgroup: nenhuma protecao ativa ainda".to_string()),
            }
            lines
        }
        Some(&"APPLY") => memory_apply(state),
        Some(&"PROTECT") => match rest.get(1).and_then(|s| s.parse::<u64>().ok()) {
            Some(bytes) => memory_protect_running_server(state, bytes),
            None => vec!["ERRO uso: MEMORY PROTECT <bytes>".to_string()],
        },
        Some(other) => vec![format!("ERRO subcomando MEMORY desconhecido: {other}")],
    }
}

fn memory_apply(state: &State) -> Vec<String> {
    let mut lines = Vec::new();

    match memory::apply_profile(&state.damon_dir, state.hardware.profile()) {
        Ok(p) => lines.push(format!(
            "damon_reclaim: aplicado enabled={} min_age_ms={} quota_ms={} quota_sz_bytes={}",
            p.enabled, p.min_age_ms, p.quota_ms, p.quota_sz_bytes
        )),
        Err(e) => lines.push(format!("damon_reclaim: nao aplicado ({e})")),
    }

    let pid_file = state.run_dir.join("ia-server.pid");
    match memory::read_pid_file(&pid_file) {
        Some(pid) if memory::is_pid_alive(pid) => {
            match model::active_model_entry(&state.data_dir) {
                Some(entry) => {
                    let overrides = config::load_runtime_conf(&state.data_dir);
                    let factor = overrides
                        .get("IA_MEM_FLOOR_PERCENT")
                        .and_then(|v| v.parse().ok())
                        .unwrap_or(memory::DEFAULT_FLOOR_PERCENT);
                    let floor = memory::floor_bytes_for_model(entry.size_bytes, factor);
                    match memory::protect_pid(&state.cgroup_root, pid, floor) {
                    Ok(()) => lines.push(format!(
                        "cgroup: pid={pid} protegido com memory.low={floor} bytes (modelo={}, fator={factor}%)",
                        entry.name
                    )),
                    Err(e) => lines.push(format!("cgroup: nao aplicado ({e})")),
                }
                }
                None => {
                    lines.push("cgroup: nenhum modelo ativo para calcular a protecao".to_string())
                }
            }
        }
        Some(_) => {
            lines.push("cgroup: ia-server.pid encontrado mas o processo nao esta ativo".to_string())
        }
        None => lines.push("cgroup: ia-server nao esta em execucao (nada a proteger)".to_string()),
    }

    lines
}

fn memory_protect_running_server(state: &State, floor_bytes: u64) -> Vec<String> {
    let pid_file = state.run_dir.join("ia-server.pid");
    match memory::read_pid_file(&pid_file).filter(|&pid| memory::is_pid_alive(pid)) {
        Some(pid) => match memory::protect_pid(&state.cgroup_root, pid, floor_bytes) {
            Ok(()) => vec![format!(
                "cgroup: pid={pid} protegido com memory.low={floor_bytes} bytes"
            )],
            Err(e) => vec![format!("ERRO {e}")],
        },
        None => vec!["ERRO ia-server nao esta em execucao".to_string()],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hardware::HardwareInfo;
    use std::fs;

    fn test_state(tag: &str) -> State {
        let dir = env::temp_dir().join(format!("ai-core-main-test-{tag}-{}", process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(dir.join("models")).unwrap();
        fs::create_dir_all(dir.join("config")).unwrap();
        // damon_dir/cgroup_root/run_dir apontam para diretórios comuns,
        // não para sysfs/cgroupfs reais — este ambiente de
        // desenvolvimento não tem damon_reclaim nem cgroup v2 montados
        // (ver memory.rs). run_dir fica vazio por padrão (sem
        // ia-server.pid), simulando "ia-server não está em execução".
        fs::create_dir_all(dir.join("run")).unwrap();

        State {
            data_dir: dir.clone(),
            hardware: HardwareInfo {
                cpu_model: "Xeon de teste".into(),
                cpu_threads: 12,
                ram_total_kb: 16 * 1024 * 1024,
                gpu: None,
            },
            backend_mode: Mutex::new(BackendMode::Auto),
            // porta sem servidor nenhum escutando — suficiente para os
            // testes de dispatch, que só verificam enfileiramento/status,
            // não o conteúdo de uma resposta real do llama-server (isso é
            // coberto em agent.rs com um servidor de mentira).
            agent_manager: AgentManager::spawn("127.0.0.1:1".to_string()),
            damon_dir: dir.join("damon-does-not-exist"),
            cgroup_root: dir.join("cgroup"),
            run_dir: dir.join("run"),
        }
    }

    #[test]
    fn ping_returns_pong() {
        let state = test_state("ping");
        assert_eq!(dispatch("PING", &state), vec!["PONG".to_string()]);
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn unknown_command_reports_error() {
        let state = test_state("unknown");
        let resp = dispatch("BANANA", &state);
        assert_eq!(resp.len(), 1);
        assert!(resp[0].starts_with("ERRO"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn model_list_reports_empty_when_no_models() {
        let state = test_state("emptylist");
        let resp = dispatch("MODEL LIST", &state);
        assert_eq!(resp, vec!["nenhum modelo em /data/models".to_string()]);
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn backend_set_auto_then_get_reflects_change() {
        let state = test_state("backendset");
        let resp = dispatch("BACKEND SET cpu", &state);
        assert!(resp[0].contains("modo=cpu"));

        let resp = dispatch("BACKEND GET", &state);
        assert!(resp[0].contains("modo=cpu"));
        assert!(resp[0].contains("resolvido=cpu"));

        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn status_includes_agent_and_memory_summary_lines() {
        let state = test_state("status");
        let resp = dispatch("STATUS", &state);
        assert!(resp.iter().any(|l| l.contains("multiagente")));
        assert!(resp
            .iter()
            .any(|l| l.contains("memoria_damon=indisponivel")));
        assert!(resp.iter().any(|l| l.contains("memoria_protegida=false")));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn agent_roles_lists_all_planned_roles() {
        let state = test_state("agentroles");
        let resp = dispatch("AGENT ROLES", &state);
        assert_eq!(resp.len(), agent::PLANNED_ROLES.len());
        assert!(resp[0].contains("planejador"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn agent_task_enqueues_and_status_reports_it() {
        let state = test_state("agenttask");
        let resp = dispatch("AGENT TASK programador escreva um teste", &state);
        assert_eq!(resp.len(), 1);
        assert!(resp[0].starts_with("tarefa "));
        assert!(resp[0].contains("papel=programador"));

        let id_str = resp[0]
            .trim_start_matches("tarefa ")
            .split_whitespace()
            .next()
            .unwrap();

        let status_resp = dispatch(&format!("AGENT STATUS {id_str}"), &state);
        assert!(status_resp[0].contains(&format!("id={id_str}")));
        assert!(status_resp[0].contains("papel=programador"));

        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn agent_task_with_unknown_role_is_an_error() {
        let state = test_state("agentbadrole");
        let resp = dispatch("AGENT TASK inexistente faça algo", &state);
        assert_eq!(resp.len(), 1);
        assert!(resp[0].starts_with("ERRO"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn agent_status_for_unknown_id_is_an_error() {
        let state = test_state("agentstatusmissing");
        let resp = dispatch("AGENT STATUS 99999", &state);
        assert_eq!(resp.len(), 1);
        assert!(resp[0].starts_with("ERRO"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn agent_list_empty_reports_no_tasks() {
        let state = test_state("agentlistempty");
        let resp = dispatch("AGENT LIST", &state);
        assert_eq!(resp, vec!["nenhuma tarefa enfileirada ainda".to_string()]);
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn memory_status_reports_damon_unavailable_and_no_protection() {
        let state = test_state("memorystatus");
        let resp = dispatch("MEMORY STATUS", &state);
        assert!(resp[0].contains("indisponivel"));
        assert!(resp[1].contains("nenhuma protecao ativa"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn memory_apply_reports_damon_failure_and_no_server_running() {
        let state = test_state("memoryapply");
        let resp = dispatch("MEMORY APPLY", &state);
        assert!(resp[0].starts_with("damon_reclaim: nao aplicado"));
        assert!(resp[1].contains("ia-server nao esta em execucao"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn memory_apply_protects_running_server_with_active_model() {
        let state = test_state("memoryapplyfull");
        fs::write(
            state.data_dir.join("models").join("m.gguf"),
            vec![0u8; 1000],
        )
        .unwrap();
        model::set_active_by_index(&state.data_dir, 1).unwrap();
        fs::write(
            state.run_dir.join("ia-server.pid"),
            process::id().to_string(),
        )
        .unwrap();

        let resp = dispatch("MEMORY APPLY", &state);
        let cgroup_line = resp
            .iter()
            .find(|l| l.starts_with("cgroup:"))
            .expect("linha de cgroup ausente");
        assert!(cgroup_line.contains("protegido"));
        assert!(cgroup_line.contains("memory.low=1500 bytes")); // 1000 * 150%

        let (low, procs) = memory::read_protection_status(&state.cgroup_root).unwrap();
        assert_eq!(low, 1500);
        assert_eq!(procs, vec![process::id()]);

        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn memory_protect_without_running_server_is_an_error() {
        let state = test_state("memoryprotectnoserver");
        let resp = dispatch("MEMORY PROTECT 1000", &state);
        assert_eq!(resp.len(), 1);
        assert!(resp[0].starts_with("ERRO"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }

    #[test]
    fn memory_protect_with_running_server_sets_floor() {
        let state = test_state("memoryprotectok");
        fs::write(
            state.run_dir.join("ia-server.pid"),
            process::id().to_string(),
        )
        .unwrap();

        let resp = dispatch("MEMORY PROTECT 2048", &state);
        assert!(resp[0].contains("memory.low=2048 bytes"));

        let (low, _) = memory::read_protection_status(&state.cgroup_root).unwrap();
        assert_eq!(low, 2048);

        fs::remove_dir_all(&state.data_dir).unwrap();
    }
}
