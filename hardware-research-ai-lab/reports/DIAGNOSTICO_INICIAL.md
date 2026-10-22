# Diagnóstico inicial (Fase 0)

Data: 2026-10-22. Gerado executando `hrail doctor`, `hrail hardware list` e `hrail tools check` no ambiente de criação.

## Ambiente examinado

Uma **VM de nuvem (Linux 6.18, Intel Xeon 2,8 GHz, 4 CPUs lógicas, ~16 GiB de RAM, discos virtio)**.
**Não é a máquina de referência do projeto.** Portanto:

- **Nenhuma GPU foi detectada** (11 dispositivos PCI, todos virtio; nenhum de classe display; sem `/dev/dri`).
- **A RX 580 2048SP não foi observada.** O perfil dela só foi exercitado com **dados fictícios** (`origin=fixture`) em testes.
  Nenhum campo de GPU real (revisão PCI, VRAM, limites de compute, extensões Vulkan) foi validado em hardware.
- CPU: flags lidas de `/proc/cpuinfo`; esta VM **tem** AVX/AVX2, mas isso não vale para a CPU de referência, para a qual
  o HRAIL não presume AVX2 (consulta `cpu.features.avx2` em cada máquina).
- Executado como `root` (aviso do doctor); o HRAIL não usa sudo.

## Ferramentas (`hrail tools check`)

| Estado | Ferramentas |
|---|---|
| disponível | go 1.26.0, git 2.43.0, gcc 13.3.0, python3 3.13.16 |
| ausente | lspci, vulkaninfo, radv-icd (manifesto), glslangValidator, glslc, spirv-val/dis/opt, ollama, llama-cli, llama-server, gem5, mgpusim |
| não testado (por definição) | nir, aco (componentes internos do Mesa, sem binário independente) |
| incompatível | nenhuma |

Consequência: Vulkan, Mesa/RADV, compiladores de shader, simuladores e provedores de IA **não puderam ser verificados**;
os comandos correspondentes informam a ausência sem falhar.

## Fontes de pesquisa

8 fontes catalogadas e estruturalmente válidas. **Nenhuma foi verificada online** — o proxy do ambiente bloqueou
`api.github.com` e `gitlab.freedesktop.org` (HTTP 403 / falha de túnel). Logo: existência e autenticidade **não confirmadas**,
`último commit consultado` vazio, licenças marcadas como `license_verified=false`. `PS5_Vulkan` recebe tratamento de fonte
não confiável (sem execução).

## Limitações observadas

- Sem temperatura (sem sensores na VM). O autoteste registra `temp_celsius` ausente.
- Sem verificação do primeiro hardware (RX 580 2048SP) — **fazer na máquina real**: `hrail hardware inspect --salvar`.
- O formato do `vulkaninfo` varia entre versões; o parser é tolerante e foi testado só com saída fictícia no formato esperado.

## Próxima ação recomendada (na máquina de referência)

```sh
./bin/hrail doctor && ./bin/hrail init && ./bin/hrail hardware inspect --salvar --saida reports/hardware_inspect.json
```
