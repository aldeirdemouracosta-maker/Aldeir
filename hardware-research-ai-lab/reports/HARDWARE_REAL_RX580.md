# Hardware real — primeira medição (Windows, 2026-10-22)

Origem: `scripts/coletar-windows.ps1` rodado pelo usuário (WMI/CIM, kernel32, `vulkaninfo --summary`). **Dados medidos, não fixture.**
Coletor Windows ≠ inventário Linux; campos de Linux (`sysfs`, driver do kernel, Mesa) não existem aqui.

## Confirmado
| Item | Valor |
|---|---|
| GPU | **AMD Radeon RX 580 2048SP** (nome reportado pelo driver e pelo Vulkan) |
| PCI | `1002:6fdf`, subsistema `1002:0b31`, revisão `0xef` |
| Driver | AMD proprietário (Adrenalin) `31.0.21925.1001` (2026-05-19); Vulkan driverInfo `26.5.2` |
| Vulkan | instância 1.4.363; dispositivo **API 1.3.260**; `DRIVER_ID_AMD_PROPRIETARY`; conformance 1.3.3.1; discreta |
| CPU | Intel Xeon E5-2630L v2 (6 núcleos / 12 threads); **AVX sim, AVX2 NÃO**, AVX-512 não |
| RAM | 34 287 820 800 bytes (≈ 31,9 GiB) |
| Outra GPU | NVIDIA GeForce 210 (`10de:0a65`, driver 2015) — sem Vulkan; **selecionar a GPU por PCI ID** nos benchmarks |
| SO | Windows 10 Enterprise 10.0.19045 |

## Perfil completo (segunda coleta: `HRAIL-Diagnostico.zip`, `vulkaninfo` completo, mesma máquina)
Dados lidos do arquivo enviado (CPU/GPU/Sistema/Vulkan; **sem nome do PC, usuário ou números de série**; UUIDs/LUID do driver foram redigidos na fixture de teste).

| Item | Valor medido |
|---|---|
| **VRAM** | heap device-local de **7,75 GiB** (8 321 499 136 B) + janela de **256 MiB** visível à CPU = **8 GiB exatos**. Heap de sistema: 15,72 GiB |
| Resizable BAR | **não habilitado**: só 256 MiB de VRAM acessíveis diretamente pela CPU |
| Limites de compute | memória compartilhada **32 KiB**; **1024** invocações por workgroup; tamanho do workgroup 1024×1024×1024; contagem de workgroups 4294967295 × 65535 × 65535; push constants 128 B; `subgroupSize` **64** (wave64, mín. = máx. = 64) |
| Filas | família 0: gráficos+compute+transferência ×1; família 1: **compute assíncrono ×2**; família 2: transferência ×2 |
| Tipos numéricos (driver Windows) | `shaderFloat16` **false**; `shaderInt8` true; `shaderInt16`/`Int64`/`Float64` true; acesso a buffers de 8/16 bits true; atomics int64 true; **`shaderIntegerDotProduct` true**; `bufferDeviceAddress` true |
| Matriz cooperativa | **ausente** (nenhuma extensão `cooperative_matrix` entre as 144 do dispositivo) |
| Extensões úteis | `VK_KHR_shader_integer_dot_product`, `VK_KHR_16bit_storage`, `VK_KHR_8bit_storage`, `VK_KHR_shader_float16_int8`, `VK_KHR_buffer_device_address`, `VK_EXT_memory_budget`, `VK_AMD_shader_core_properties(2)` |
| Resolução de timestamps | `timestampPeriod = 40` (≈ 40 ns por tick) — relevante para medir kernels curtos |

### Leitura para IA e benchmarks (com ressalvas)
- Sem FP16 aritmético **neste driver**: cargas de IA via Vulkan cairão em FP32 e em caminhos inteiros. Int8 + dot-product existem e podem servir à quantização — **a medir (Fase 4)**.
- **Isto vale para o driver proprietário do Windows.** Sob Linux/RADV os recursos expostos podem ser diferentes; refaça a coleta lá antes de concluir.
- **Contagem de CUs ainda desconhecida.** O `vulkaninfo` não imprime `VkPhysicalDeviceShaderCorePropertiesAMD`; a extensão `VK_AMD_shader_core_properties` existe e pode ser consultada na Fase 4. O nome "2048SP" sugere 2048 stream processors (≈ 32 CUs de 64) — **inferência, não medida**.
- **Comparação com o modelo simulado (Fase 2):** o modelo padrão do MGPUSim é R9 Nano (64 CUs, HBM, 4 GB). A placa real tem 8 GiB de memória gráfica e `subgroupSize` 64 (coerente com wave64 de GCN), mas as demais diferenças (CUs, clocks, caches, GDDR5×HBM) **não estão calibradas**.

## Consequências para o laboratório
1. A tabela interna acertou: `1002:6fdf` = RX 580 2048SP (**observado em 1 máquina**; revisão `0xef`, subsistema `1002:0b31`).
2. **Não há RADV/Mesa/ACO nesta máquina no Windows**: driver proprietário, compilador próprio. Compiler-lab (Fase 3) e RADV só se aplicam sob **Linux** (Ubuntu Live no pen drive).
3. **Sem AVX2** na CPU (AVX sim): llama.cpp na CPU usará no máximo AVX.
4. `adapter_ram_bytes_wmi` (≈ 4 GiB) é o limite de 32 bits do WMI; a VRAM real é a do `vulkaninfo` (8 GiB), derivada da soma dos heaps device-local.
5. Selecionar a GPU por PCI ID nos benchmarks (há uma GeForce 210 sem Vulkan na máquina).

## Defeitos do HRAIL achados com os dados reais (corrigidos, com testes)
1. O coletor PowerShell misturava stderr do loader Vulkan no JSON (corrigido antes).
2. **Arrays em linhas separadas** (`maxComputeWorkGroupCount: count = 3` + valores) eram lidos como o texto `count = 3` → agora `4294967295,65535,65535`.
3. **Heaps de memória** eram guardados só como números, sem indicar quais são device-local → agora há heaps/tipos estruturados e `VRAMFromHeaps()` (derivação declarada, nunca sobrescreve leitura direta do sysfs).
4. **Superfícies de apresentação** (`GPU id : 0 (...) [VK_KHR_win32_surface]:`) eram tomadas por um dispositivo vazio: o arquivo original gerava um perfil de GPU vazio. A fixture aparada que escrevi primeiro havia cortado esse trecho e **mascarou o defeito**; só apareceu ao importar o arquivo original. A fixture agora inclui o trecho como regressão.
5. `apiVersion` vinha com sufixo `(4206852)`; normalizado para `1.3.260`.

Novo: `hrail hardware importar --vulkan ARQ [--salvar]` importa um `vulkaninfo` (UTF-8 ou UTF-16 do PowerShell) como perfil **parcial** (`source: importado`), declarando o que não existe (revisão PCI, driver do kernel, CPU, RAM).
