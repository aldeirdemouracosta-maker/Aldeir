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

## Consequências para o laboratório
1. A tabela interna acertou: `1002:6fdf` = RX 580 2048SP (agora **observado** em 1 máquina; a revisão `0xef` e o nome vieram do driver).
2. **Não há RADV/Mesa/ACO nesta máquina no Windows**: o driver é proprietário, com compilador próprio. Compiler-lab (Fase 3) e RADV só se aplicam sob **Linux** (Ubuntu Live no pen drive ou instalação).
3. **Sem AVX2**: llama.cpp na CPU usará no máximo AVX; confirmado o cuidado de não presumir AVX2.
4. `adapter_ram_bytes_wmi = 4 293 918 720` (≈ 4 GiB) é o **limite de 32 bits do WMI**, não a VRAM real. A VRAM real ainda NÃO foi medida (o script atualizado lê o registro do driver; `vulkaninfo` completo traz os heaps).
5. Ainda desconhecidos: limites de compute, filas, `subgroupSize`, tipos numéricos (fp16/int8/int64), extensões do dispositivo e heaps de memória — exigem a saída completa do `vulkaninfo`.

## Defeito encontrado no coletor (corrigido)
`2>&1` misturou avisos do loader Vulkan (stderr) e uma mensagem de erro do PowerShell no campo `vulkaninfo_summary`. Corrigido: stderr descartado; saída completa vai para `reports/vulkaninfo_windows.txt`. Leitura da VRAM via registro adicionada (**não testada**).
