# CPU/GPU Intel

**Status CPU:** suportado (rota padrão — backend CPU do llama.cpp).

**Status GPU integrada (iGPU):** não integrado nesta versão. O
`hardware.rs` do `ai-core` detecta o vendor `0x8086` em
`/sys/class/drm` apenas para fins de diagnóstico (`ia-gpu status`
reporta a presença, mas `backend.rs` só resolve para `vulkan` quando o
vendor é `0x1002` — AMD). Adicionar Vulkan via ANV (driver Intel do Mesa)
é candidato natural para uma versão futura, seguindo o mesmo padrão já
usado para AMD/RADV.

Rede Intel (e1000/e1000e) já está habilitada em
`kernel/config/physical.fragment`.
