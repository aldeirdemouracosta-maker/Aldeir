//! Telemetria e regra adaptativa do AI Scheduler (etapa 0.8).
//!
//! Diferença importante em relação a `memory.rs`/`scheduler.rs`: as
//! leituras deste módulo (`/proc/loadavg`, `/proc/meminfo`) **não**
//! precisam de caminho parametrizável por variável de ambiente, porque
//! `/proc` existe e é legível neste próprio ambiente de desenvolvimento
//! — mesmo padrão já usado por `hardware.rs` desde a 0.4 (que lê
//! `/proc/cpuinfo`/`/proc/meminfo` diretamente). O que não existe aqui é
//! o cgroup v2 e o DAMON, não o `/proc`.
//!
//! `adapt_weight` é uma regra determinística se-então que reage a essas
//! métricas mais o histórico de tokens/s do `AgentManager`
//! (`agent.rs::tokens_per_second_stats`) — **não é aprendizado por
//! reforço nem qualquer forma de ML**. O roadmap descreve esta etapa
//! como "um passo em direção ao aprendizado, não apenas regras fixas":
//! é exatamente isso — telemetria real alimentando uma decisão que
//! antes (0.7) era só um valor estático por perfil de hardware. Um
//! scheduler que de fato aprende (ajustando parâmetros a partir de
//! recompensa observada) continua sendo trabalho futuro.

use std::fs;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Telemetry {
    pub load1: Option<f64>,
    pub mem_available_kb: Option<u64>,
}

pub fn collect() -> Telemetry {
    let loadavg = fs::read_to_string("/proc/loadavg").unwrap_or_default();
    let meminfo = fs::read_to_string("/proc/meminfo").unwrap_or_default();
    Telemetry {
        load1: parse_loadavg(&loadavg),
        mem_available_kb: parse_mem_available_kb(&meminfo),
    }
}

/// Extrai a média de carga de 1 minuto (primeiro campo de
/// `/proc/loadavg`, formato `"0.23 0.06 0.02 1/102 862"`).
pub fn parse_loadavg(content: &str) -> Option<f64> {
    content.split_whitespace().next()?.parse().ok()
}

/// Extrai `MemAvailable` (em kB) de um `/proc/meminfo` — estimativa do
/// kernel de memória disponível sem entrar em swap, mais realista que
/// `MemFree` sozinho.
pub fn parse_mem_available_kb(content: &str) -> Option<u64> {
    for line in content.lines() {
        if let Some(rest) = line.strip_prefix("MemAvailable:") {
            let digits: String = rest.chars().filter(|c| c.is_ascii_digit()).collect();
            if let Ok(kb) = digits.parse::<u64>() {
                return Some(kb);
            }
        }
    }
    None
}

pub fn load_per_core(load1: f64, cpu_threads: u32) -> f64 {
    if cpu_threads == 0 {
        0.0
    } else {
        load1 / cpu_threads as f64
    }
}

const LOW_MEM_RATIO_THRESHOLD: f64 = 0.10;
const HIGH_LOAD_PER_CORE_THRESHOLD: f64 = 1.0;
const LOW_LOAD_PER_CORE_THRESHOLD: f64 = 0.5;
const THROUGHPUT_DROP_RATIO: f64 = 0.7;
const THROUGHPUT_OK_RATIO: f64 = 0.95;
pub const MAX_ADAPTIVE_WEIGHT: u32 = 2000;

#[derive(Debug, Clone, Copy)]
pub struct AdaptInput {
    /// Peso do perfil de hardware (`scheduler::weight_for_profile`) —
    /// piso: a regra nunca reduz o peso abaixo disso.
    pub base_weight: u32,
    /// Peso atualmente aplicado ao cgroup (`scheduler::read_weight`).
    pub current_weight: u32,
    pub load_per_core: f64,
    /// Média recente de tokens/s (`AgentManager::tokens_per_second_stats`).
    pub current_tokens_per_sec: Option<f64>,
    /// Melhor tokens/s já observado nesta sessão do daemon.
    pub best_tokens_per_sec: Option<f64>,
    /// `mem_available_kb / ram_total_kb` — `None` quando indisponível.
    pub mem_available_ratio: Option<f64>,
}

/// Regra determinística (não é aprendizado): se o throughput recente
/// caiu bem abaixo do melhor já observado nesta sessão, E há contenção
/// real de CPU, E a memória não está criticamente baixa, aumenta a
/// prioridade do cgroup do modelo em 50% (capado em
/// `MAX_ADAPTIVE_WEIGHT`). Se o throughput está bom e sobra CPU, relaxa
/// de volta para o peso base do perfil. Caso contrário — inclusive sem
/// amostras de tokens/s ainda — mantém o peso atual (nunca abaixo do
/// peso base).
pub fn adapt_weight(input: AdaptInput) -> u32 {
    let floor = input.current_weight.max(input.base_weight);

    let (current_tps, best_tps) = match (input.current_tokens_per_sec, input.best_tokens_per_sec) {
        (Some(c), Some(b)) if b > 0.0 => (c, b),
        _ => return floor,
    };

    let ratio = current_tps / best_tps;
    let mem_critical = input
        .mem_available_ratio
        .is_some_and(|r| r < LOW_MEM_RATIO_THRESHOLD);

    if ratio < THROUGHPUT_DROP_RATIO
        && input.load_per_core > HIGH_LOAD_PER_CORE_THRESHOLD
        && !mem_critical
    {
        let boosted = input
            .current_weight
            .saturating_add(input.current_weight / 2);
        boosted.min(MAX_ADAPTIVE_WEIGHT).max(floor)
    } else if ratio > THROUGHPUT_OK_RATIO && input.load_per_core < LOW_LOAD_PER_CORE_THRESHOLD {
        input.base_weight
    } else {
        floor
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_loadavg_first_field() {
        assert_eq!(parse_loadavg("0.23 0.06 0.02 1/102 862\n"), Some(0.23));
    }

    #[test]
    fn empty_loadavg_is_none() {
        assert_eq!(parse_loadavg(""), None);
    }

    #[test]
    fn parses_mem_available() {
        let meminfo = "MemTotal:       16336548 kB\nMemAvailable:   15866792 kB\n";
        assert_eq!(parse_mem_available_kb(meminfo), Some(15866792));
    }

    #[test]
    fn missing_mem_available_is_none() {
        assert_eq!(parse_mem_available_kb("MemTotal: 1000 kB\n"), None);
    }

    #[test]
    fn load_per_core_divides_by_threads() {
        assert_eq!(load_per_core(4.0, 4), 1.0);
        assert_eq!(load_per_core(2.0, 8), 0.25);
    }

    #[test]
    fn load_per_core_zero_threads_does_not_divide_by_zero() {
        assert_eq!(load_per_core(4.0, 0), 0.0);
    }

    fn base_input() -> AdaptInput {
        AdaptInput {
            base_weight: 400,
            current_weight: 400,
            load_per_core: 0.0,
            current_tokens_per_sec: None,
            best_tokens_per_sec: None,
            mem_available_ratio: None,
        }
    }

    #[test]
    fn without_tokens_data_holds_at_floor() {
        let input = AdaptInput {
            current_weight: 600,
            base_weight: 400,
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 600);
    }

    #[test]
    fn low_throughput_with_cpu_contention_boosts_weight() {
        let input = AdaptInput {
            current_weight: 400,
            base_weight: 400,
            load_per_core: 1.5,
            current_tokens_per_sec: Some(5.0),
            best_tokens_per_sec: Some(10.0), // ratio 0.5 < 0.7
            mem_available_ratio: Some(0.5),
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 600); // 400 + 400/2
    }

    #[test]
    fn boost_is_capped_at_max_adaptive_weight() {
        let input = AdaptInput {
            current_weight: 1900,
            base_weight: 400,
            load_per_core: 2.0,
            current_tokens_per_sec: Some(1.0),
            best_tokens_per_sec: Some(10.0),
            mem_available_ratio: Some(0.5),
            ..base_input()
        };
        assert_eq!(adapt_weight(input), MAX_ADAPTIVE_WEIGHT);
    }

    #[test]
    fn low_throughput_but_no_cpu_contention_does_not_boost() {
        let input = AdaptInput {
            current_weight: 400,
            base_weight: 400,
            load_per_core: 0.2, // sem contenção
            current_tokens_per_sec: Some(5.0),
            best_tokens_per_sec: Some(10.0),
            mem_available_ratio: Some(0.5),
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 400);
    }

    #[test]
    fn low_throughput_with_contention_but_critical_memory_does_not_boost() {
        let input = AdaptInput {
            current_weight: 400,
            base_weight: 400,
            load_per_core: 1.5,
            current_tokens_per_sec: Some(5.0),
            best_tokens_per_sec: Some(10.0),
            mem_available_ratio: Some(0.05), // < 10%: memória crítica
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 400);
    }

    #[test]
    fn good_throughput_with_idle_cpu_relaxes_to_base() {
        let input = AdaptInput {
            current_weight: 800,
            base_weight: 400,
            load_per_core: 0.1,
            current_tokens_per_sec: Some(9.8),
            best_tokens_per_sec: Some(10.0), // ratio 0.98 > 0.95
            mem_available_ratio: Some(0.5),
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 400);
    }

    #[test]
    fn good_throughput_with_cpu_still_busy_holds_current_weight() {
        let input = AdaptInput {
            current_weight: 800,
            base_weight: 400,
            load_per_core: 1.2, // ainda ocupado — não relaxa
            current_tokens_per_sec: Some(9.8),
            best_tokens_per_sec: Some(10.0),
            mem_available_ratio: Some(0.5),
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 800);
    }

    #[test]
    fn middling_ratio_holds_current_weight() {
        let input = AdaptInput {
            current_weight: 500,
            base_weight: 400,
            load_per_core: 0.7,
            current_tokens_per_sec: Some(8.0),
            best_tokens_per_sec: Some(10.0), // ratio 0.8 — nem baixo nem ok
            mem_available_ratio: Some(0.5),
            ..base_input()
        };
        assert_eq!(adapt_weight(input), 500);
    }

    #[test]
    fn never_returns_below_base_weight() {
        let input = AdaptInput {
            current_weight: 100, // abaixo do peso base por algum motivo
            base_weight: 400,
            load_per_core: 0.0,
            current_tokens_per_sec: None,
            best_tokens_per_sec: None,
            mem_available_ratio: None,
        };
        assert_eq!(adapt_weight(input), 400);
    }
}
