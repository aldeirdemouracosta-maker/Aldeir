//! Detecção de hardware (CPU, RAM, GPU) e seleção de perfil de execução.
//!
//! As funções de parsing recebem o conteúdo já lido (e não o caminho do
//! arquivo) para que possam ser testadas com dados de exemplo, sem
//! depender de `/proc` real.

use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Profile {
    Tiny,   // < 6 GB RAM
    Low,    // 6-12 GB
    Medium, // 12-24 GB
    Large,  // 24 GB+
}

impl Profile {
    pub fn label(&self) -> &'static str {
        match self {
            Profile::Tiny => "TINY",
            Profile::Low => "LOW",
            Profile::Medium => "MEDIUM",
            Profile::Large => "LARGE",
        }
    }

    /// Contexto (n_ctx) sugerido para llama.cpp neste perfil.
    pub fn suggested_ctx(&self) -> u32 {
        match self {
            Profile::Tiny => 1024,
            Profile::Low => 2048,
            Profile::Medium => 4096,
            Profile::Large => 8192,
        }
    }

    pub fn suggested_model(&self) -> &'static str {
        match self {
            Profile::Tiny => "~0.3-1B Q4 (ex.: Qwen3.5 0.8B)",
            Profile::Low => "~0.8-1.5B Q4",
            Profile::Medium => "~1.5-4B Q4 (ex.: SmolLM3 3B, Gemma 3 4B)",
            Profile::Large => "~4-8B Q4 com offload GPU",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GpuInfo {
    pub driver: String,
    pub render_node: String,
    pub is_amd: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HardwareInfo {
    pub cpu_model: String,
    pub cpu_threads: u32,
    pub ram_total_kb: u64,
    pub gpu: Option<GpuInfo>,
}

impl HardwareInfo {
    pub fn profile(&self) -> Profile {
        ram_profile(self.ram_total_kb)
    }

    pub fn ram_total_gb(&self) -> f64 {
        self.ram_total_kb as f64 / 1024.0 / 1024.0
    }

    /// Threads recomendadas para inferência CPU: todas menos uma, para
    /// deixar folga ao ai-core/ia-shell, com mínimo de 1.
    pub fn suggested_threads(&self) -> u32 {
        self.cpu_threads.saturating_sub(1).max(1)
    }
}

pub fn detect() -> HardwareInfo {
    let cpuinfo = fs::read_to_string("/proc/cpuinfo").unwrap_or_default();
    let meminfo = fs::read_to_string("/proc/meminfo").unwrap_or_default();

    let (cpu_model, cpu_threads) = parse_cpuinfo(&cpuinfo);
    let ram_total_kb = parse_meminfo_total_kb(&meminfo);
    let gpu = detect_gpu(Path::new("/sys/class/drm"), Path::new("/dev/dri"));

    HardwareInfo {
        cpu_model,
        cpu_threads,
        ram_total_kb,
        gpu,
    }
}

/// Extrai `model name` e conta linhas `processor` de um `/proc/cpuinfo`.
pub fn parse_cpuinfo(content: &str) -> (String, u32) {
    let mut model = String::from("desconhecido");
    let mut threads: u32 = 0;

    for line in content.lines() {
        if let Some(rest) = line.strip_prefix("processor") {
            if rest.trim_start().starts_with(':') {
                threads += 1;
            }
        } else if model == "desconhecido" {
            if let Some(rest) = line.strip_prefix("model name") {
                if let Some(value) = rest.trim_start().strip_prefix(':') {
                    model = value.trim().to_string();
                }
            }
        }
    }

    (model, threads)
}

/// Extrai `MemTotal` (em kB) de um `/proc/meminfo`.
pub fn parse_meminfo_total_kb(content: &str) -> u64 {
    for line in content.lines() {
        if let Some(rest) = line.strip_prefix("MemTotal:") {
            let digits: String = rest.chars().filter(|c| c.is_ascii_digit()).collect();
            if let Ok(kb) = digits.parse::<u64>() {
                return kb;
            }
        }
    }
    0
}

pub fn ram_profile(ram_total_kb: u64) -> Profile {
    let gb = ram_total_kb as f64 / 1024.0 / 1024.0;
    if gb < 6.0 {
        Profile::Tiny
    } else if gb < 12.0 {
        Profile::Low
    } else if gb < 24.0 {
        Profile::Medium
    } else {
        Profile::Large
    }
}

/// Procura uma GPU AMD em `/sys/class/drm/card*/device/vendor` (0x1002) e
/// confirma que existe um render node correspondente em `/dev/dri`.
/// Retorna `None` quando não há GPU compatível — o chamador deve então
/// usar CPU (ver `backend.rs`).
fn detect_gpu(drm_sys: &Path, dri_dev: &Path) -> Option<GpuInfo> {
    let entries = fs::read_dir(drm_sys).ok()?;
    for entry in entries.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if !name.starts_with("card") {
            continue;
        }
        let vendor_path = entry.path().join("device/vendor");
        let vendor = fs::read_to_string(&vendor_path).unwrap_or_default();
        let vendor = vendor.trim();
        if vendor.eq_ignore_ascii_case("0x1002") {
            let render_node = dri_dev.join("renderD128");
            let render_node_str = render_node.to_string_lossy().to_string();
            return Some(GpuInfo {
                driver: "amdgpu".to_string(),
                render_node: render_node_str,
                is_amd: true,
            });
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_CPUINFO: &str = "\
processor\t: 0
vendor_id\t: GenuineIntel
model name\t: Intel(R) Xeon(R) CPU E5-2650 v2 @ 2.60GHz
processor\t: 1
model name\t: Intel(R) Xeon(R) CPU E5-2650 v2 @ 2.60GHz
processor\t: 2
processor\t: 3
";

    const SAMPLE_MEMINFO: &str = "\
MemTotal:       16336548 kB
MemFree:         8321244 kB
MemAvailable:   14012332 kB
";

    #[test]
    fn parses_cpuinfo_model_and_thread_count() {
        let (model, threads) = parse_cpuinfo(SAMPLE_CPUINFO);
        assert_eq!(model, "Intel(R) Xeon(R) CPU E5-2650 v2 @ 2.60GHz");
        assert_eq!(threads, 4);
    }

    #[test]
    fn parses_meminfo_total() {
        assert_eq!(parse_meminfo_total_kb(SAMPLE_MEMINFO), 16336548);
    }

    #[test]
    fn empty_cpuinfo_is_handled_gracefully() {
        let (model, threads) = parse_cpuinfo("");
        assert_eq!(model, "desconhecido");
        assert_eq!(threads, 0);
    }

    #[test]
    fn ram_profile_thresholds() {
        assert_eq!(ram_profile(4 * 1024 * 1024), Profile::Tiny);
        assert_eq!(ram_profile(8 * 1024 * 1024), Profile::Low);
        assert_eq!(ram_profile(16 * 1024 * 1024), Profile::Medium);
        assert_eq!(ram_profile(32 * 1024 * 1024), Profile::Large);
    }

    #[test]
    fn suggested_threads_leaves_one_core_free() {
        let hw = HardwareInfo {
            cpu_model: "test".into(),
            cpu_threads: 12,
            ram_total_kb: 16 * 1024 * 1024,
            gpu: None,
        };
        assert_eq!(hw.suggested_threads(), 11);
    }

    #[test]
    fn suggested_threads_never_zero() {
        let hw = HardwareInfo {
            cpu_model: "test".into(),
            cpu_threads: 1,
            ram_total_kb: 4 * 1024 * 1024,
            gpu: None,
        };
        assert_eq!(hw.suggested_threads(), 1);
    }
}
