//! Leitura/escrita de `$IA_DATA_DIR/config/runtime.conf` (formato
//! `CHAVE=valor`, uma por linha, `#` inicia comentário) e do modo de
//! backend persistido separadamente em `config/backend-mode`.

use std::collections::HashMap;
use std::fs;
use std::path::Path;

use crate::backend::BackendMode;

pub fn runtime_conf_path(data_dir: &Path) -> std::path::PathBuf {
    data_dir.join("config").join("runtime.conf")
}

fn backend_mode_path(data_dir: &Path) -> std::path::PathBuf {
    data_dir.join("config").join("backend-mode")
}

/// Faz o parsing de um `runtime.conf` já lido em memória. Linhas vazias ou
/// iniciadas por `#` são ignoradas; chaves são normalizadas para
/// maiúsculas.
pub fn parse_runtime_conf(content: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((key, value)) = line.split_once('=') {
            map.insert(key.trim().to_ascii_uppercase(), value.trim().to_string());
        }
    }
    map
}

pub fn load_runtime_conf(data_dir: &Path) -> HashMap<String, String> {
    let content = fs::read_to_string(runtime_conf_path(data_dir)).unwrap_or_default();
    parse_runtime_conf(&content)
}

/// Carrega o modo de backend persistido (`config/backend-mode`); usa
/// `auto` quando o arquivo não existe ou contém valor inválido.
pub fn load_backend_mode(data_dir: &Path) -> BackendMode {
    match fs::read_to_string(backend_mode_path(data_dir)) {
        Ok(content) => BackendMode::parse(&content).unwrap_or(BackendMode::Auto),
        Err(_) => BackendMode::Auto,
    }
}

pub fn save_backend_mode(data_dir: &Path, mode: BackendMode) -> Result<(), String> {
    let cfg_dir = data_dir.join("config");
    fs::create_dir_all(&cfg_dir).map_err(|e| format!("não foi possível criar {cfg_dir:?}: {e}"))?;
    fs::write(backend_mode_path(data_dir), mode.to_string())
        .map_err(|e| format!("não foi possível gravar modo de backend: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_key_value_lines_ignoring_comments_and_blanks() {
        let content = "\
# comentário
IA_THREADS=8

ia_ctx = 2048
IA_BATCH=256
";
        let map = parse_runtime_conf(content);
        assert_eq!(map.get("IA_THREADS"), Some(&"8".to_string()));
        assert_eq!(map.get("IA_CTX"), Some(&"2048".to_string()));
        assert_eq!(map.get("IA_BATCH"), Some(&"256".to_string()));
        assert_eq!(map.len(), 3);
    }

    #[test]
    fn empty_content_yields_empty_map() {
        assert!(parse_runtime_conf("").is_empty());
    }

    #[test]
    fn backend_mode_roundtrip() {
        let dir = std::env::temp_dir().join(format!("ai-core-config-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();

        assert_eq!(load_backend_mode(&dir), BackendMode::Auto);

        save_backend_mode(&dir, BackendMode::Vulkan).unwrap();
        assert_eq!(load_backend_mode(&dir), BackendMode::Vulkan);

        fs::remove_dir_all(&dir).unwrap();
    }
}
