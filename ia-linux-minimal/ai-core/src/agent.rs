//! Placeholder do gerenciador multiagente (etapa 0.5 do roadmap).
//!
//! Nesta versão (0.4) o `ai-core` ainda não gerencia múltiplos agentes
//! simultâneos — apenas hardware, modelos e backend. Este módulo existe
//! para que `STATUS` já reporte o estado real ("não implementado") em vez
//! de simular uma funcionalidade que ainda não existe, e para fixar a
//! interface que a etapa 0.5 vai implementar.

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
            AgentRole::Critico => "crítico",
            AgentRole::Executor => "executor",
        }
    }
}

/// Todos os papéis definidos para a futura etapa 0.5, na ordem em que
/// aparecerão em `AGENT LIST` quando implementado.
pub const PLANNED_ROLES: [AgentRole; 5] = [
    AgentRole::Planejador,
    AgentRole::Programador,
    AgentRole::Pesquisador,
    AgentRole::Critico,
    AgentRole::Executor,
];

pub fn status_line() -> String {
    format!(
        "multiagente: não implementado (roadmap 0.5) — papéis planejados: {}",
        PLANNED_ROLES
            .iter()
            .map(|r| r.label())
            .collect::<Vec<_>>()
            .join(", ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_line_lists_all_planned_roles() {
        let line = status_line();
        for role in PLANNED_ROLES {
            assert!(line.contains(role.label()));
        }
    }
}
