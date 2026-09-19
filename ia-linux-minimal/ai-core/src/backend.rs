//! Seleção do backend de inferência (CPU ou Vulkan), com fallback
//! automático quando não há GPU compatível — ver docs/architecture.md,
//! seção "AUTO".

use crate::hardware::HardwareInfo;
use std::fmt;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackendMode {
    Auto,
    Cpu,
    Vulkan,
}

impl BackendMode {
    pub fn parse(s: &str) -> Option<BackendMode> {
        match s.trim().to_ascii_lowercase().as_str() {
            "auto" => Some(BackendMode::Auto),
            "cpu" => Some(BackendMode::Cpu),
            "vulkan" => Some(BackendMode::Vulkan),
            _ => None,
        }
    }
}

impl fmt::Display for BackendMode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            BackendMode::Auto => "auto",
            BackendMode::Cpu => "cpu",
            BackendMode::Vulkan => "vulkan",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResolvedBackend {
    Cpu,
    Vulkan,
}

impl fmt::Display for ResolvedBackend {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            ResolvedBackend::Cpu => "cpu",
            ResolvedBackend::Vulkan => "vulkan",
        };
        write!(f, "{s}")
    }
}

/// Resolve o modo configurado (auto/cpu/vulkan) para um backend concreto,
/// considerando o hardware detectado. `vulkan` explícito sem GPU cai para
/// CPU (fallback), nunca falha — ver decisão de arquitetura em
/// docs/architecture.md.
pub fn resolve(mode: BackendMode, hw: &HardwareInfo) -> ResolvedBackend {
    match mode {
        BackendMode::Cpu => ResolvedBackend::Cpu,
        BackendMode::Vulkan => {
            if gpu_ready(hw) {
                ResolvedBackend::Vulkan
            } else {
                ResolvedBackend::Cpu
            }
        }
        BackendMode::Auto => {
            if gpu_ready(hw) {
                ResolvedBackend::Vulkan
            } else {
                ResolvedBackend::Cpu
            }
        }
    }
}

fn gpu_ready(hw: &HardwareInfo) -> bool {
    match &hw.gpu {
        Some(gpu) => gpu.is_amd && Path::new(&gpu.render_node).exists(),
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::GpuInfo;

    fn hw_with_gpu(render_node_exists_path: &str) -> HardwareInfo {
        HardwareInfo {
            cpu_model: "test".into(),
            cpu_threads: 8,
            ram_total_kb: 16 * 1024 * 1024,
            gpu: Some(GpuInfo {
                driver: "amdgpu".into(),
                render_node: render_node_exists_path.into(),
                is_amd: true,
            }),
        }
    }

    fn hw_without_gpu() -> HardwareInfo {
        HardwareInfo {
            cpu_model: "test".into(),
            cpu_threads: 8,
            ram_total_kb: 16 * 1024 * 1024,
            gpu: None,
        }
    }

    #[test]
    fn parses_all_valid_modes() {
        assert_eq!(BackendMode::parse("auto"), Some(BackendMode::Auto));
        assert_eq!(BackendMode::parse("CPU"), Some(BackendMode::Cpu));
        assert_eq!(BackendMode::parse("Vulkan"), Some(BackendMode::Vulkan));
        assert_eq!(BackendMode::parse("nonsense"), None);
    }

    #[test]
    fn cpu_mode_always_resolves_to_cpu() {
        let hw = hw_with_gpu("/dev/null"); // path existe no host de teste
        assert_eq!(resolve(BackendMode::Cpu, &hw), ResolvedBackend::Cpu);
    }

    #[test]
    fn auto_without_gpu_falls_back_to_cpu() {
        let hw = hw_without_gpu();
        assert_eq!(resolve(BackendMode::Auto, &hw), ResolvedBackend::Cpu);
    }

    #[test]
    fn vulkan_requested_without_render_node_falls_back_to_cpu() {
        let hw = hw_with_gpu("/path/that/does/not/exist/renderD128");
        assert_eq!(resolve(BackendMode::Vulkan, &hw), ResolvedBackend::Cpu);
    }

    #[test]
    fn auto_with_ready_gpu_resolves_to_vulkan() {
        let hw = hw_with_gpu("/dev/null");
        assert_eq!(resolve(BackendMode::Auto, &hw), ResolvedBackend::Vulkan);
    }
}
