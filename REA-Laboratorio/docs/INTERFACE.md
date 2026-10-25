# Interface — REA Shell

## Identidade visual
Simplicidade e legibilidade, inspiradas na clareza do ecossistema Go, **sem usar marca, logotipo nem personagem de terceiros**.
Paleta: azul `#1E6FD9`, azul-claro `#EAF2FD`, branco `#FFFFFF`, cinza-azulado `#5B6B7F` para texto secundário; amarelo
`#F4C430` somente no capacete do mascote. Contraste do texto ≥ 4,5:1.

**Mascote original — "Toupeira Engenheira":** toupeira simpática, capacete amarelo de engenheiro, segurando uma chave de fenda.
Entrega em SVG vetorial autoral (criado do zero, com licença do projeto) + versão ASCII de 8 linhas para terminal.
Usos: tela inicial, estados vazios, "analisando…". Nunca como único indicador de estado.

## Tecnologia (decisão provisória)
GTK3 via Python (`python3-gi`): suporte a AT-SPI (leitores de tela) e navegação por teclado melhor que Tk, consumo moderado.
**Gate:** medir RAM ociosa no Fluxbox; meta < 150 MB para a shell. Se estourar, avaliar Tk com camada de acessibilidade própria.
Sem navegador embutido nem Electron.

## Telas
1. **Início:** botões grandes — *Full REA*, *Abrir arquivo/pasta*, *Laboratórios*, *Projetos*, *IA*, *Terminal*.
2. **Laboratórios:** grade dos 15 módulos com selo real: `Disponível` / `Instalável` / `Quebrado (motivo)` / `Planejado`.
3. **Tarefa em andamento:** etapas, log, cancelar; ao fim, link do relatório (SHA-256, evidências, proveniência).
4. **Painel IA:** motor (llama.cpp / Ollama / LM Studio / OpenAI-compatível), endereço, modelo, backend detectado
   (CPU/Vulkan/CUDA), botão *Testar conexão*; aviso explícito quando o motor é remoto (dados saem do computador).
5. **Modo Oficina:** banner laranja permanente; só opera em cópias de trabalho.
6. **Terminal acessível:** terminal único, fonte grande ajustável, alto contraste, sem dependência de mouse.

## Teclado e acessibilidade
Tab/Shift+Tab em ordem lógica; atalhos com Alt+letra sublinhada; F1 ajuda; Esc cancela; foco sempre visível; todos os controles
com nome acessível; textos em português do Brasil; sem informação só por cor.

## Regra BUTTON_EXISTS != BUTTON_WORKS
Um botão só é habilitado se o verificador do módulo correspondente retornou `disponivel` nesta sessão. Caso contrário fica
desabilitado com a razão ("Ghidra não encontrado em REA-MODULES"). Ao clicar, o resultado real (sucesso/erro) é exibido —
nunca uma confirmação fixa. Cada botão tem um teste de aceite automatizado ligado ao seu módulo.

## Motores de IA (AI Bridge) — contrato de adaptador
`detectar() -> {presente, versão, backends[]}`, `modelos() -> []`, `completar(msgs) -> texto|erro_classificado`.
| Adaptador | Endpoint | Observação |
|---|---|---|
| llama.cpp | processo local `llama-server` (API compatível com OpenAI) | compilar sem AVX2; Vulkan/CUDA só se detectados |
| Ollama | `127.0.0.1:11434` | modelos instalados via API |
| LM Studio | API local ou de rede (endereço configurável) | remoto exige autorização |
| OpenAI-compatível | URL + chave (guardada só em memória/arquivo protegido do usuário) | remoto exige autorização |
CPU sempre disponível; Vulkan via `vulkaninfo`; CUDA via driver NVIDIA (fora da ISO; módulo externo). Nada é presumido: o painel
mostra o que a detecção realmente encontrou. O sistema inicia e funciona sem nenhum modelo.
