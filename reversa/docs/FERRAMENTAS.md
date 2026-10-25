# Catálogo de ferramentas e plano de integração

Legenda de confiança: **V** = verificado em fonte nesta sessão (README ou listagem); **C** = conhecimento
geral, não verificado agora; **?** = vindo de terceiros, sem confirmação.

## Por função no `reversa`

| Função | Ferramenta | Como entra | Conf. |
|---|---|---|---|
| Estático | Ghidra (+ `ghidra_psx_ldr`) | `Backend` headless; depois processo persistente | V |
| Estático | Rizin / Cutter | `Backend` por subprocesso (`rizin -qc`) | C |
| Estático | radare2 | `Backend` por subprocesso (`r2 -q -c`); licença LGPLv3 em sua maior parte | V |
| Estático | Binary Ninja | Opcional (licença comercial); só se o usuário tiver | ? |
| Dinâmico | PCSX-Redux | `Backend` pelo servidor web do emulador; resolve `jalr` | V |
| Dinâmico | BizHawk (mcp-bizhawk) | `Backend` para outros consoles | V (listagem) |
| Divisão de ROM | splat | Subprocesso; alimenta os operários por segmento | V |
| Firmware | binwalk, unblob, OFRAK | Etapa de extração antes da análise | C |
| Firmware | UEFITool, CHIPSEC | Fora do foco (UEFI/plataforma) | C |
| Android | JADX / apktool | `Backend` para APK | C |
| Decompilação por IA | LLM4Decompile | Comparar com o nosso estágio 2 | C |
| IA local + Ghidra | OGhidra, reverser_ai | Referência de projeto (Ollama + Ghidra) | V (lista) |
| MCP existentes | GhidraMCP, pyghidra-mcp, radare2-mcp | Referência; podemos expor o `reversa` como MCP | V |
| Orquestração | REA, Open-ReverseLab | Referência de desenho | V |
| GPU NVIDIA | Envytools | Fora do escopo | C |

## Open-ReverseLab (LING71671)
- Plataforma de agente + servidor MCP com "100+" ferramentas e artigos de base de conhecimento, GPL-3.0.
- Integra Ghidra, Frida, x64dbg, Rizin, jadx, Cutter, YARA e também ferramentas ofensivas (sqlmap, nuclei, ffuf).
- **Cuidados:** o README recomenda exclusões no antivírus do Windows para a pasta de ferramentas; o agente
  coleta um perfil do ambiente local (SO, variáveis, rede). Revise `install_tools` antes de rodar, use VM.
- **Para nós:** só como referência de desenho. Não copiar código: GPL-3.0 contaminaria o nosso projeto.

## Awesome AI Reverse Engineering (zhuyansen)
- Lista com 118 (README) ou 122 (sobre) repositórios; 74 são MCPs de desmontadores.
- Nenhuma entrada é específica de PS1/consoles. O mais próximo é `vgrichina/re-skill` (skill para jogos retrô).
- Úteis para IA local: `mrphrazer/reverser_ai` (LLM local), `llnl/OGhidra` (Ollama + Ghidra),
  `mrphrazer/ghidra-headless-mcp`.

## Licenças: regra prática
Chame as ferramentas como **processos externos** (rizin, radare2, Cutter, Ghidra) e não copie nem ligue o
código delas ao nosso. O próprio radare2 recomenda usar r2pipe para quem não é GPL. Isso mantém o `reversa`
livre para escolher a licença. (Orientação técnica, não consultoria jurídica.)

## Ordem sugerida
1. Backend PCSX-Redux (dinâmico, resolve saltos indiretos).
2. Backend rizin/radare2 (alternativa leve ao Ghidra, boa para o contêiner sem JVM).
3. Ghidra persistente com loader PS1.
4. Extração de firmware (binwalk/unblob) como pré-estágio.
5. Servidor MCP do `reversa`.
