# GPU AMD

**Status:** suportado (rota principal desde a etapa 0.3).

```
GPU AMD (GCN 1.1+ / RDNA)
   ↓
kernel: CONFIG_DRM_AMDGPU (kernel/config/physical.fragment)
   ↓
firmware: linux-firmware (blob redistribuível — ver docs/licenses.md)
   ↓
Mesa RADV (BR2_PACKAGE_MESA3D_VULKAN_DRIVER_AMD)
   ↓
Vulkan Loader + llama.cpp (backend Vulkan)
```

Sem ROCm: RADV cobre a linha GCN/RDNA sem exigir a pilha ROCm, o que é
particularmente relevante para GPUs mais antigas (ex.: RX 580 / Polaris),
onde o suporte ROCm upstream é limitado ou inexistente.

Verificação em runtime: `ia-gpu status`, `ia-gpu vulkaninfo`.
