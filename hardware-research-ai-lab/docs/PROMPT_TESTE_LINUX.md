# Prompt para testar o HRAIL em Linux (máquina com a RX 580 2048SP)

Copie o texto abaixo (entre as linhas ====) e entregue a um agente (ex.: Claude Code) rodando NA máquina Linux com a placa.

====
Você é um engenheiro de testes. Valide, em Linux e na máquina real, o projeto Hardware Research AI Lab (HRAIL).
Seu trabalho é TESTAR E RELATAR, não consertar nem avançar de fase. Responda em português.

REGRAS OBRIGATÓRIAS
- Não use sudo, não instale pacotes, não altere kernel, módulos, firmware, BIOS, initramfs, drivers, clocks, tensão ou energia da GPU, e não instale Mesa experimental. Se faltar algum pacote, PARE essa etapa e peça ao usuário para instalar (ele roda o comando).
- Não modifique o código do projeto para fazer teste passar. Se algo falhar, registre o comando, a saída e a causa provável. Pode PROPOR um patch no relatório, sem aplicá-lo.
- Não faça commit/push. Escreva apenas dentro da pasta do projeto.
- Não execute código de terceiros sem aprovação humana: na etapa do MGPUSim você NUNCA roda `simulation aprovar`; quem aprova é o usuário, com o nome dele.
- Não avance para a Fase 3. Não invente valores: o que não foi medido deve ficar como "não medido".
- Use timeout em comandos longos. Não cole no relatório nome de usuário, hostname, caminhos pessoais nem números de série.

PREPARO
1. Obtenha o código: branch `claude/amazing-cray-f5twmo` do repositório `aldeirdemouracosta-maker/Aldeir`; entre em `hardware-research-ai-lab/`.
2. Leia `README.md`, `docs/IMPLANTACAO.md` e `reports/HARDWARE_REAL_RX580.md` (valores esperados medidos no Windows).
3. Verifique se existem: `go` (>= 1.24; o toolchain 1.26 é baixado automaticamente, precisa de rede), `git`, `vulkaninfo` (pacote vulkan-tools), `lspci` (opcional) e o driver Vulkan RADV (mesa-vulkan-drivers). Liste o que faltar e peça ao usuário para instalar.

ETAPA 1 — Suíte de testes
4. Rode `./scripts/validar.sh`. Esperado: gofmt sem diferenças, vet limpo, 87 testes sem falhas, build ok. Qualquer falha: registre o teste e a saída. Testes que pulam por falta de python3/git/unshare devem ser listados.

ETAPA 2 — Hardware real (somente leitura)
5. Execute, nesta ordem: `./bin/hrail doctor`, `./bin/hrail init`, `./bin/hrail hardware list`,
   `./bin/hrail hardware inspect --salvar --saida reports/hardware_inspect_linux.json`, `./bin/hrail tools check`,
   `./bin/hrail benchmark selftest`, `./bin/hrail compiler info`, `./bin/hrail agents check`, `./bin/hrail report generate`.
6. Guarde também: `vulkaninfo > reports/vulkaninfo_linux.txt 2>&1` e `vulkaninfo --summary`.
7. Confira contra o esperado (marque OK / DIVERGE / NÃO MEDIDO para cada item):
   - GPU PCI `1002:6fdf`, revisão `0xef`, subsistema `1002:0b31`; nome contendo "RX 580 2048SP"; `known_variant` = requer_verificacao.
   - Driver do kernel `amdgpu`; versão do kernel; VRAM total pelo sysfs (esperado ~8 GiB) e VRAM visível à CPU (esperado 256 MiB se Resizable BAR estiver desligado).
   - Vulkan: driver `radv` (NÃO o proprietário), versão do Mesa, API Vulkan, `subgroupSize`, `maxComputeSharedMemorySize` (Windows: 32768), `maxComputeWorkGroupInvocations` (1024), filas, número de extensões.
   - Tipos numéricos no RADV: `shaderFloat16`, `shaderInt8`, `shaderIntegerDotProduct`, `storageBuffer16BitAccess` — compare com o Windows (FP16 aritmético = false; dot product = true) e destaque QUALQUER diferença.
   - CPU: AVX2 deve ser falso (Xeon E5-2630L v2); confirme em `cpu.features`.
   - Existe uma GeForce 210 na máquina: confirme que aparece como segunda GPU e que o perfil da RX 580 não foi misturado com ela.
   - Temperatura: `benchmark selftest` achou sensor (hwmon amdgpu)? Informe a fonte ou "indisponível".
   - PCIe: velocidade/largura do link atuais e máximas.
   - Ferramentas ausentes (glslangValidator, spirv-*, ollama, llama.cpp, gem5…) devem aparecer como "ausente", sem erro.
8. Confirme que `./bin/hrail doctor` termina com código 0 e que nenhum comando alterou o sistema.

ETAPA 3 — Fase 1 (rede, somente leitura)
9. Rode `./bin/hrail research verificar --online --clonar --profundidade 50`. Esperado: github.com verificado (mgpusim, gem5-repo, vulkan-samples, llama-cpp, ps5-vulkan); registre se gitlab.freedesktop.org (Mesa), www.gem5.org e docs.mesa3d.org ficaram acessíveis nesta rede. Depois `./bin/hrail research historico --fonte mesa --palavras polaris,gfx8,gfx803,radv,aco` se o Mesa foi clonado, e `./bin/hrail research commits --revertidos`.

ETAPA 4 — Fase 2 (SÓ PREPARO E REVISÃO)
10. Rode `./bin/hrail simulation preparar` e `./bin/hrail simulation revisar --amostra fir`. Resuma ao usuário a lista de imports sensíveis e os achados manuais.
11. PARE. Mostre ao usuário o comando `hrail simulation aprovar --amostra fir --commit <hash> --por "nome do usuário"` e aguarde. Só depois que o usuário aprovar (ele mesmo executa), e confirmar que aceita baixar ~330 MB, rode `./bin/hrail simulation compilar --autorizo-codigo-terceiros` e `./bin/hrail simulation rodar --autorizo-codigo-terceiros --repeticoes 3`. Esperado: kernel_time = 7,747e-06 s idêntico nas 3 execuções, "verificado pelo próprio simulador: true", rede isolada = true (se `unshare -n` falhar, informe e NÃO use --permitir-sem-isolamento sem perguntar).

ENTREGA
12. Gere `reports/RELATORIO_TESTE_LINUX.md` com: ambiente (distro, kernel, versões de go/git/mesa, SEM hostname/usuário); tabela etapa × comando × resultado (OK/FALHA/DIVERGE/NÃO MEDIDO); divergências em relação ao Windows e ao esperado; falhas com saída; limitações; e uma lista curta de bugs ou melhorias propostas (sem aplicar).
13. Empacote `reports/` (exceto qualquer arquivo com dados pessoais; confira com grep por usuário, hostname e "serial") em `HRAIL-Linux-Diagnostico.tar.gz` e diga ao usuário onde ele está para enviá-lo de volta.
====

Depois de receber o pacote, a análise dos dados reais sob Linux/RADV alimenta o planejamento da Fase 3.
