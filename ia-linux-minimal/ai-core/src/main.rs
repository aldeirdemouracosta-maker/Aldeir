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
mod model;

use std::env;
use std::path::PathBuf;
use std::process;
use std::sync::Mutex;

use backend::{BackendMode, ResolvedBackend};
use hardware::HardwareInfo;

const VERSION: &str = env!("CARGO_PKG_VERSION");
const DEFAULT_SOCKET: &str = "/run/ia-core.sock";
const DEFAULT_DATA_DIR: &str = "/data";

pub struct State {
    data_dir: PathBuf,
    hardware: HardwareInfo,
    backend_mode: Mutex<BackendMode>,
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

    let state = std::sync::Arc::new(State {
        data_dir,
        hardware: hw,
        backend_mode: Mutex::new(backend_mode),
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
        agent::status_line(),
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

        State {
            data_dir: dir,
            hardware: HardwareInfo {
                cpu_model: "Xeon de teste".into(),
                cpu_threads: 12,
                ram_total_kb: 16 * 1024 * 1024,
                gpu: None,
            },
            backend_mode: Mutex::new(BackendMode::Auto),
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
    fn status_ends_with_agent_placeholder_line() {
        let state = test_state("status");
        let resp = dispatch("STATUS", &state);
        assert!(resp.last().unwrap().contains("multiagente"));
        fs::remove_dir_all(&state.data_dir).unwrap();
    }
}
