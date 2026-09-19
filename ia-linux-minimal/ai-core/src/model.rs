//! Gerenciamento de modelos GGUF em `$IA_DATA_DIR/models`. Os modelos
//! nunca ficam dentro da imagem do sistema — ver docs/architecture.md.

use std::fs;
use std::path::{Path, PathBuf};

use crate::hardware::Profile;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelEntry {
    pub name: String,
    pub path: PathBuf,
    pub size_bytes: u64,
}

pub fn models_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("models")
}

fn active_model_file(data_dir: &Path) -> PathBuf {
    data_dir.join("config").join("active-model")
}

/// Lista os arquivos `.gguf` em `$data_dir/models`, ordenados por nome
/// para que os índices usados por `MODEL SELECT <n>` sejam estáveis entre
/// chamadas.
pub fn list_models(data_dir: &Path) -> Vec<ModelEntry> {
    let dir = models_dir(data_dir);
    let mut entries = Vec::new();

    let read_dir = match fs::read_dir(&dir) {
        Ok(rd) => rd,
        Err(_) => return entries,
    };

    for entry in read_dir.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("gguf") {
            continue;
        }
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();
        let size_bytes = entry.metadata().map(|m| m.len()).unwrap_or(0);
        entries.push(ModelEntry {
            name,
            path,
            size_bytes,
        });
    }

    entries.sort_by(|a, b| a.name.cmp(&b.name));
    entries
}

/// Lê o nome do modelo ativo persistido em `config/active-model`, se
/// existir e ainda corresponder a um arquivo presente na lista atual.
pub fn active_model(data_dir: &Path) -> Option<String> {
    let content = fs::read_to_string(active_model_file(data_dir)).ok()?;
    let name = content.trim().to_string();
    if name.is_empty() {
        return None;
    }
    Some(name)
}

/// Marca o modelo de índice `idx` (1-based, como exibido por `MODEL LIST`)
/// como ativo, persistindo o nome em `config/active-model`.
pub fn set_active_by_index(data_dir: &Path, idx: usize) -> Result<String, String> {
    let models = list_models(data_dir);
    if idx == 0 || idx > models.len() {
        return Err(format!(
            "índice inválido: {idx} (existem {} modelos)",
            models.len()
        ));
    }
    let chosen = &models[idx - 1];

    let cfg_dir = data_dir.join("config");
    fs::create_dir_all(&cfg_dir).map_err(|e| format!("não foi possível criar {cfg_dir:?}: {e}"))?;
    fs::write(active_model_file(data_dir), &chosen.name)
        .map_err(|e| format!("não foi possível gravar modelo ativo: {e}"))?;

    Ok(chosen.name.clone())
}

pub fn recommend(profile: Profile) -> &'static str {
    profile.suggested_model()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::File;
    use std::io::Write;

    fn tmp_data_dir(tag: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("ai-core-model-test-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(dir.join("models")).unwrap();
        fs::create_dir_all(dir.join("config")).unwrap();
        dir
    }

    fn write_gguf(dir: &Path, name: &str, bytes: &[u8]) {
        let mut f = File::create(dir.join("models").join(name)).unwrap();
        f.write_all(bytes).unwrap();
    }

    #[test]
    fn lists_only_gguf_files_sorted_by_name() {
        let dir = tmp_data_dir("list");
        write_gguf(&dir, "zeta.gguf", b"aa");
        write_gguf(&dir, "alpha.gguf", b"bbbb");
        File::create(dir.join("models").join("notes.txt")).unwrap();

        let models = list_models(&dir);
        assert_eq!(models.len(), 2);
        assert_eq!(models[0].name, "alpha.gguf");
        assert_eq!(models[0].size_bytes, 4);
        assert_eq!(models[1].name, "zeta.gguf");

        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn missing_models_dir_returns_empty_list() {
        let dir = std::env::temp_dir().join("ai-core-model-test-missing-dir-does-not-exist");
        let _ = fs::remove_dir_all(&dir);
        assert!(list_models(&dir).is_empty());
    }

    #[test]
    fn set_active_by_index_persists_and_rejects_out_of_range() {
        let dir = tmp_data_dir("select");
        write_gguf(&dir, "a.gguf", b"1");
        write_gguf(&dir, "b.gguf", b"22");

        let chosen = set_active_by_index(&dir, 2).unwrap();
        assert_eq!(chosen, "b.gguf");
        assert_eq!(active_model(&dir), Some("b.gguf".to_string()));

        assert!(set_active_by_index(&dir, 0).is_err());
        assert!(set_active_by_index(&dir, 99).is_err());

        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn active_model_none_when_file_absent() {
        let dir = tmp_data_dir("noactive");
        assert_eq!(active_model(&dir), None);
        fs::remove_dir_all(&dir).unwrap();
    }
}
