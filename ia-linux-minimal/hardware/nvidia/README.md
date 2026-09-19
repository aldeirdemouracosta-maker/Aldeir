# GPU NVIDIA

**Status:** não suportado nesta versão.

O driver NVIDIA proprietário não é redistribuível pela GPL do kernel
Linux nem pelas licenças do Buildroot da forma simples que
`linux-firmware`/Mesa permitem para AMD, e o driver aberto `nouveau` não
oferece desempenho competitivo de Vulkan para inferência. Por isso GPUs
NVIDIA hoje caem no fallback CPU automático (`backend.rs::resolve`),
exatamente como qualquer hardware sem GPU compatível.

`hardware/detect.sh` (e `ai-core HW`) ainda relatam a presença de uma GPU
NVIDIA (vendor `0x10de`) para fins de diagnóstico, mas nenhum backend
Vulkan é oferecido para ela.

Se este suporte for adicionado no futuro, a rota mais provável é Vulkan
via driver proprietário NVIDIA redistribuído pelo próprio usuário fora da
imagem do sistema (mesma filosofia de "modelos GGUF ficam fora do SO"
aplicada a blobs binários não redistribuíveis).
