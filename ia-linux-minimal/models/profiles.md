# Tabela de perfis (referência)

Espelha as constantes em `ai-core/src/hardware.rs` (`Profile`). Se você
mudar os limiares ali, atualize esta tabela também — não há geração
automática nesta versão.

| Perfil | Limite de RAM       | `suggested_ctx()` | Threads sugeridas          |
|--------|----------------------|--------------------:|------------------------------|
| TINY   | RAM < 6 GB           | 1024                 | `cpu_threads - 1` (mín. 1)   |
| LOW    | 6 GB ≤ RAM < 12 GB   | 2048                 | idem                         |
| MEDIUM | 12 GB ≤ RAM < 24 GB  | 4096                 | idem                         |
| LARGE  | RAM ≥ 24 GB          | 8192                 | idem                         |

Threads sugeridas deixam sempre 1 núcleo livre para `ai-core`/`ia-shell`
e o restante do sistema — ver `HardwareInfo::suggested_threads` e o
teste `suggested_threads_leaves_one_core_free` em
`ai-core/src/hardware.rs`.

Overrides manuais (por exemplo, CPU sem AVX2 preferindo menos threads do
que o sugerido) vão em `/data/config/runtime.conf` — ver os exemplos em
`configs/*.conf` e `ai-core/src/config.rs`.
