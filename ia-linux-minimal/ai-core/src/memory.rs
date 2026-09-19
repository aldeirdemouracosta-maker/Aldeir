//! AI Memory (etapa 0.6).
//!
//! Duas responsabilidades, deliberadamente separadas:
//!
//! 1. **Ajustar `DAMON_RECLAIM`** por perfil de hardware
//!    (`ai-core/src/hardware.rs::Profile`) — hardware com pouca RAM
//!    reclama páginas frias mais cedo e com mais orçamento de I/O;
//!    hardware com bastante RAM fica mais conservador. Interface: os
//!    arquivos de parâmetro simples do módulo `damon_reclaim`
//!    (`enabled`, `min_age`, `quota_ms`, `quota_sz` — ver
//!    `Documentation/admin-guide/mm/damon/reclaim.rst` no kernel), não a
//!    hierarquia sysfs completa de kdamonds/contexts/schemes, que é bem
//!    mais complexa e não haveria como validar aqui (ver nota abaixo).
//!
//! 2. **Proteger a memória do modelo ativo/KV cache** contra reclaim
//!    agressivo — via cgroups v2 `memory.low` no processo do
//!    `llama-server` (PID lido de `/run/ia-server.pid`, mesmo arquivo que
//!    `rootfs-overlay/usr/bin/ia-server` escreve), não via filtros de
//!    memcg do DAMON (existem, mas exigem a hierarquia sysfs completa de
//!    schemes, que é significativamente mais complexa). `memory.low` é o
//!    mecanismo padrão do kernel para proteger a memória de um cgroup sob
//!    pressão de reclaim, e cobre tanto o reclaim comum quanto o reclaim
//!    proativo do DAMON_RECLAIM, que reutiliza o caminho comum de reclaim
//!    do kernel.
//!
//! Nota honesta: este ambiente de desenvolvimento não tem
//! `/sys/module/damon_reclaim/parameters` nem cgroup v2 montado (ver
//! docs/build.md) — não foi possível testar contra o kernel real. Por
//! isso todos os caminhos sysfs/cgroupfs são parametrizáveis (via
//! `IA_DAMON_SYSFS`, `IA_CGROUP_ROOT` em main.rs), e os testes deste
//! módulo usam diretórios temporários simulando a mesma estrutura de
//! arquivos simples, não o kernel de verdade.

use std::fs;
use std::path::{Path, PathBuf};

use crate::hardware::Profile;

pub const DEFAULT_DAMON_RECLAIM_DIR: &str = "/sys/module/damon_reclaim/parameters";
pub const DEFAULT_CGROUP_ROOT: &str = "/sys/fs/cgroup/ia-linux";
const PROTECTED_CGROUP_NAME: &str = "model";

/// Fração padrão de folga acima do tamanho do arquivo `.gguf` do modelo
/// ativo usada como piso de proteção (`memory.low`), para cobrir KV cache
/// e buffers de inferência. Heurística inicial, não medida — ajustável
/// via `IA_MEM_FLOOR_PERCENT` em `/data/config/runtime.conf`.
pub const DEFAULT_FLOOR_PERCENT: u64 = 150;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DamonReclaimParams {
    pub enabled: bool,
    pub min_age_ms: u64,
    pub quota_ms: u64,
    pub quota_sz_bytes: u64,
}

impl DamonReclaimParams {
    /// Heurísticas iniciais por perfil, não valores medidos em hardware
    /// real: perfis com menos RAM reclamam páginas frias mais cedo
    /// (`min_age_ms` menor) e com mais orçamento de I/O por ciclo
    /// (`quota_ms`/`quota_sz_bytes` maiores); `LARGE` fica mais
    /// conservador, já que sobra RAM e reclaim proativo desnecessário só
    /// gera I/O extra.
    pub fn for_profile(profile: Profile) -> DamonReclaimParams {
        match profile {
            Profile::Tiny => DamonReclaimParams {
                enabled: true,
                min_age_ms: 60_000,
                quota_ms: 50,
                quota_sz_bytes: 10 * 1024 * 1024,
            },
            Profile::Low => DamonReclaimParams {
                enabled: true,
                min_age_ms: 90_000,
                quota_ms: 50,
                quota_sz_bytes: 20 * 1024 * 1024,
            },
            Profile::Medium => DamonReclaimParams {
                enabled: true,
                min_age_ms: 180_000,
                quota_ms: 30,
                quota_sz_bytes: 20 * 1024 * 1024,
            },
            Profile::Large => DamonReclaimParams {
                enabled: true,
                min_age_ms: 300_000,
                quota_ms: 10,
                quota_sz_bytes: 10 * 1024 * 1024,
            },
        }
    }
}

fn read_param(dir: &Path, name: &str) -> Option<String> {
    fs::read_to_string(dir.join(name)).ok()
}

fn write_param(dir: &Path, name: &str, value: &str) -> Result<(), String> {
    let path = dir.join(name);
    fs::write(&path, value).map_err(|e| format!("falha ao escrever {}: {e}", path.display()))
}

/// Lê o estado atual de `damon_reclaim` em `dir`. Retorna `None` quando
/// os arquivos não existem — interpretado pelo chamador como "módulo não
/// carregado neste kernel", não como erro fatal.
pub fn read_status(dir: &Path) -> Option<DamonReclaimParams> {
    let enabled = read_param(dir, "enabled")?;
    let min_age_ms = read_param(dir, "min_age")?.trim().parse().ok()?;
    let quota_ms = read_param(dir, "quota_ms")?.trim().parse().ok()?;
    let quota_sz_bytes = read_param(dir, "quota_sz")?.trim().parse().ok()?;
    Some(DamonReclaimParams {
        enabled: enabled.trim() == "Y",
        min_age_ms,
        quota_ms,
        quota_sz_bytes,
    })
}

/// Aplica os parâmetros do perfil de hardware a `dir`. Falha (Err) sem
/// pânico quando `dir` não existe ou não é gravável — esperado neste
/// ambiente de desenvolvimento e em qualquer kernel sem `damon_reclaim`
/// carregado.
pub fn apply_profile(dir: &Path, profile: Profile) -> Result<DamonReclaimParams, String> {
    let params = DamonReclaimParams::for_profile(profile);
    write_param(dir, "enabled", if params.enabled { "Y" } else { "N" })?;
    write_param(dir, "min_age", &params.min_age_ms.to_string())?;
    write_param(dir, "quota_ms", &params.quota_ms.to_string())?;
    write_param(dir, "quota_sz", &params.quota_sz_bytes.to_string())?;
    Ok(params)
}

pub fn protected_cgroup_dir(cgroup_root: &Path) -> PathBuf {
    cgroup_root.join(PROTECTED_CGROUP_NAME)
}

/// Cria (se necessário) o cgroup de proteção, define `memory.low` como
/// `floor_bytes` e move `pid` para dentro dele.
pub fn protect_pid(cgroup_root: &Path, pid: u32, floor_bytes: u64) -> Result<(), String> {
    let dir = protected_cgroup_dir(cgroup_root);
    fs::create_dir_all(&dir).map_err(|e| format!("falha ao criar {}: {e}", dir.display()))?;
    write_param(&dir, "memory.low", &floor_bytes.to_string())?;
    write_param(&dir, "cgroup.procs", &pid.to_string())?;
    Ok(())
}

/// Lê `memory.low` e os PIDs atualmente no cgroup de proteção. `None`
/// quando o cgroup ainda não foi criado (nenhuma proteção ativa ainda).
pub fn read_protection_status(cgroup_root: &Path) -> Option<(u64, Vec<u32>)> {
    let dir = protected_cgroup_dir(cgroup_root);
    let memory_low = read_param(&dir, "memory.low")?.trim().parse().ok()?;
    let procs = read_param(&dir, "cgroup.procs")?
        .lines()
        .filter_map(|l| l.trim().parse().ok())
        .collect();
    Some((memory_low, procs))
}

/// Piso de proteção = tamanho do arquivo do modelo × `factor_percent` /
/// 100 — a folga cobre KV cache e buffers de inferência (não medidos
/// diretamente; ver `DEFAULT_FLOOR_PERCENT`).
pub fn floor_bytes_for_model(model_size_bytes: u64, factor_percent: u64) -> u64 {
    model_size_bytes.saturating_mul(factor_percent) / 100
}

pub fn is_pid_alive(pid: u32) -> bool {
    Path::new(&format!("/proc/{pid}")).exists()
}

pub fn read_pid_file(path: &Path) -> Option<u32> {
    fs::read_to_string(path).ok()?.trim().parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("ai-core-memory-test-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn read_status_is_none_when_files_missing() {
        let dir = tmp_dir("missingfiles");
        assert_eq!(read_status(&dir), None);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn apply_profile_then_read_status_roundtrips() {
        let dir = tmp_dir("roundtrip");
        let applied = apply_profile(&dir, Profile::Low).unwrap();
        let read_back = read_status(&dir).unwrap();
        assert_eq!(applied, read_back);
        assert!(read_back.enabled);
        assert_eq!(read_back.min_age_ms, 90_000);
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn apply_profile_scales_min_age_with_ram() {
        let tiny = DamonReclaimParams::for_profile(Profile::Tiny);
        let low = DamonReclaimParams::for_profile(Profile::Low);
        let medium = DamonReclaimParams::for_profile(Profile::Medium);
        let large = DamonReclaimParams::for_profile(Profile::Large);
        assert!(tiny.min_age_ms < low.min_age_ms);
        assert!(low.min_age_ms < medium.min_age_ms);
        assert!(medium.min_age_ms < large.min_age_ms);
    }

    #[test]
    fn apply_profile_fails_gracefully_on_nonexistent_dir() {
        let dir = std::env::temp_dir().join("ai-core-memory-test-does-not-exist-at-all");
        let _ = fs::remove_dir_all(&dir);
        assert!(apply_profile(&dir, Profile::Medium).is_err());
    }

    #[test]
    fn protect_pid_creates_cgroup_and_writes_params() {
        let root = tmp_dir("cgroup");
        protect_pid(&root, 4242, 100 * 1024 * 1024).unwrap();

        let (low, procs) = read_protection_status(&root).unwrap();
        assert_eq!(low, 100 * 1024 * 1024);
        assert_eq!(procs, vec![4242]);

        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn read_protection_status_is_none_before_any_protection() {
        let root = tmp_dir("noprotectionyet");
        assert_eq!(read_protection_status(&root), None);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn floor_bytes_applies_percentage() {
        assert_eq!(floor_bytes_for_model(1000, 150), 1500);
        assert_eq!(floor_bytes_for_model(0, 150), 0);
        assert_eq!(
            floor_bytes_for_model(200 * 1024 * 1024, 100),
            200 * 1024 * 1024
        );
    }

    #[test]
    fn current_process_pid_is_alive() {
        assert!(is_pid_alive(std::process::id()));
    }

    #[test]
    fn implausible_pid_is_not_alive() {
        assert!(!is_pid_alive(999_999_999));
    }

    #[test]
    fn read_pid_file_parses_trimmed_content() {
        let dir = tmp_dir("pidfile");
        let path = dir.join("ia-server.pid");
        fs::write(&path, "  12345\n").unwrap();
        assert_eq!(read_pid_file(&path), Some(12345));
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn read_pid_file_missing_is_none() {
        let dir = tmp_dir("nopidfile");
        assert_eq!(read_pid_file(&dir.join("ia-server.pid")), None);
        fs::remove_dir_all(&dir).unwrap();
    }
}
