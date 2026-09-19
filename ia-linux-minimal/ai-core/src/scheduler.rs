//! AI Scheduler (etapa 0.7) — escopo reduzido, ver nota abaixo.
//!
//! O roadmap original (dissertação de mestrado do AI-Linux, ver
//! `kernel/patches/README.md`) imagina um scheduler experimental via
//! `sched_ext` (BPF carregado dinamicamente, com fallback automático
//! para o scheduler padrão). Isso exige uma toolchain completa de BPF
//! (clang com alvo BPF, `bpftool` para gerar `vmlinux.h` a partir do
//! BTF do kernel, um loader como `libbpf`) e um kernel com
//! `CONFIG_SCHED_CLASS_EXT` ativo. Este ambiente de desenvolvimento tem
//! `clang`, mas não tem `bpftool`, não tem `/sys/kernel/sched_ext` e não
//! tem cgroup v2 montado — não haveria como compilar, carregar nem
//! testar um scheduler BPF de verdade aqui, então eu não fingiria isso.
//!
//! Em vez disso, esta etapa entrega o que dá para construir e validar
//! de verdade agora, com o mesmo mecanismo padrão do kernel usado por
//! `memory.rs` para RAM: o controlador `cpu` de cgroup v2 (`cpu.weight`)
//! no **mesmo cgroup** que `memory.rs` já protege com `memory.low`
//! (`memory::protected_cgroup_dir`). `cpu.weight` (1-10000, padrão 100)
//! define a prioridade relativa de CPU do cgroup do modelo/llama-server
//! frente a outros cgroups do sistema — maior peso, mais fatia de CPU
//! sob contenção. Não é aprendizado por reforço nem um scheduler
//! próprio: é uma heurística estática por perfil, igual a `memory.rs`.
//! Um scheduler `sched_ext` de verdade continua sendo trabalho futuro
//! explícito — ver `kernel/patches/README.md`.

use std::fs;
use std::path::Path;

use crate::hardware::Profile;
use crate::memory;

/// Peso padrão de cgroup v2 (`cpu.weight` começa em 100 quando não
/// configurado). Damos ao cgroup do modelo um peso maior que o padrão,
/// escalado pelo perfil de hardware: perfis com menos RAM/CPU (TINY/LOW)
/// se beneficiam mais de uma prioridade alta, já que há menos folga de
/// CPU para outros processos; LARGE fica mais próximo do padrão, porque
/// sobra CPU o suficiente para não precisar competir tanto. Heurística
/// inicial, não medida em hardware real — mesmo espírito de
/// `memory::DamonReclaimParams::for_profile`.
pub const DEFAULT_WEIGHT: u32 = 100;

pub fn weight_for_profile(profile: Profile) -> u32 {
    match profile {
        Profile::Tiny => DEFAULT_WEIGHT * 8,
        Profile::Low => DEFAULT_WEIGHT * 6,
        Profile::Medium => DEFAULT_WEIGHT * 4,
        Profile::Large => DEFAULT_WEIGHT * 2,
    }
}

/// Aplica o peso do perfil ao cgroup do modelo. Atalho para
/// `apply_weight_value(cgroup_root, weight_for_profile(profile))`.
pub fn apply_weight(cgroup_root: &Path, profile: Profile) -> Result<u32, String> {
    let weight = weight_for_profile(profile);
    apply_weight_value(cgroup_root, weight)?;
    Ok(weight)
}

/// Aplica um peso explícito ao cgroup do modelo, criando-o se necessário
/// (mesmo cgroup de `memory::protect_pid` — `cpu.weight` e `memory.low`
/// convivem no mesmo diretório de cgroup v2). Usado tanto por
/// `apply_weight` (peso fixo do perfil, 0.7) quanto por `SCHED ADAPT`
/// (peso ajustado por telemetria, 0.8 — ver `telemetry::adapt_weight`).
pub fn apply_weight_value(cgroup_root: &Path, weight: u32) -> Result<(), String> {
    let dir = memory::protected_cgroup_dir(cgroup_root);
    fs::create_dir_all(&dir).map_err(|e| format!("falha ao criar {}: {e}", dir.display()))?;
    let path = dir.join("cpu.weight");
    fs::write(&path, weight.to_string())
        .map_err(|e| format!("falha ao escrever {}: {e}", path.display()))
}

/// `None` quando `cpu.weight` ainda não foi aplicado (cgroup inexistente
/// ou arquivo ainda não escrito) — interpretado pelo chamador como
/// "SCHED APPLY ainda não rodou", não como erro.
pub fn read_weight(cgroup_root: &Path) -> Option<u32> {
    let dir = memory::protected_cgroup_dir(cgroup_root);
    fs::read_to_string(dir.join("cpu.weight"))
        .ok()?
        .trim()
        .parse()
        .ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "ai-core-scheduler-test-{tag}-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn weight_scales_down_as_ram_increases() {
        let tiny = weight_for_profile(Profile::Tiny);
        let low = weight_for_profile(Profile::Low);
        let medium = weight_for_profile(Profile::Medium);
        let large = weight_for_profile(Profile::Large);
        assert!(tiny > low);
        assert!(low > medium);
        assert!(medium > large);
        assert!(large >= DEFAULT_WEIGHT);
    }

    #[test]
    fn read_weight_is_none_before_apply() {
        let root = tmp_dir("noapplyyet");
        assert_eq!(read_weight(&root), None);
    }

    #[test]
    fn apply_then_read_roundtrips() {
        let root = tmp_dir("roundtrip");
        let applied = apply_weight(&root, Profile::Medium).unwrap();
        assert_eq!(applied, 400);
        assert_eq!(read_weight(&root), Some(400));
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn apply_weight_shares_cgroup_dir_with_memory_protection() {
        let root = tmp_dir("shared");
        apply_weight(&root, Profile::Low).unwrap();
        memory::protect_pid(&root, std::process::id(), 1024).unwrap();

        // ambos escrevem no mesmo diretório de cgroup — cpu.weight
        // continua legível depois que memory.rs também escreveu ali.
        assert_eq!(read_weight(&root), Some(600));
        let (low, procs) = memory::read_protection_status(&root).unwrap();
        assert_eq!(low, 1024);
        assert_eq!(procs, vec![std::process::id()]);

        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn apply_weight_fails_gracefully_when_parent_is_not_a_directory() {
        let root = tmp_dir("badparent");
        fs::create_dir_all(&root).unwrap();
        // cria um arquivo comum onde o cgroup deveria ser um diretório
        fs::write(root.join("model"), b"nao sou um diretorio").unwrap();

        assert!(apply_weight(&root, Profile::Tiny).is_err());

        fs::remove_dir_all(&root).unwrap();
    }
}
