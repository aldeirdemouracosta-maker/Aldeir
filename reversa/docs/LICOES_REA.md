# Lições do código-fonte do REA (leitura, sem execução)

Fonte lida: clone raso de `morluto/rea` (MIT, TypeScript, ~3 mil arquivos `.ts`, ~18 mil linhas só em `src/`).
Nada do projeto foi instalado ou executado. Referência para ideias; o código do `reversa` é escrito do zero.

## O que o REA faz e vale copiar como ideia

| Ideia no REA | Estado no `reversa` |
|---|---|
| Toda resposta é uma **Evidence** com `confidence` (`observed`/`derived`/`inferred`), `limitations`, `locations`, digest e vínculos `evidence_links` | Feito: `confidence`, `digest`, `subject` (hash do alvo) e `limits`. Falta `locations` e vínculos entre evidências |
| `Unknown` explícito: o que não se sabe fica registrado, não vira "ausente" | A fazer: registro `unknown` para chamadas indiretas (`jalr`) e dados no meio do código |
| **Um provedor profundo por alvo**, escolhido de forma determinística, sem troca automática em caso de falha | A fazer: `Registry` que escolhe o backend por formato e fixa a escolha na sessão |
| Resposta mínima: resumo primeiro, evidência completa retida na sessão e paginada (`inspect_analysis_view`, `detail`) | A fazer: guardar a desmontagem completa e mandar ao modelo só o resumo, com paginação |
| Cache com chave que cobre todos os insumos do resultado, com regra de invalidação | Parcial: `llm.Cached` cobre modelo + mensagens; falta incluir hash do alvo e versão da ferramenta |
| Ghidra com **banco efêmero**, ponte `HeadlessScript` em Java e transporte NDJSON por socket Unix; lançamento com prazo, limpeza com nova tentativa | A fazer: `Ghidra` persistente falando NDJSON com um script de ponte |
| **Processos próprios**: grupo de processos, raiz privada, prazos, saída limitada, limpeza que não se perde se falhar | A fazer: `backend.run` hoje só tem timeout. Precisa de grupo de processos (`Setpgid`) e matar o grupo todo |
| Perfil de análise fixado (`-processor MIPS:LE:32:default`) quando a detecção automática erra | A fazer: fixar o idioma MIPS LE 32 no Ghidra para PS-X EXE |
| Ferramentas "traga seu próprio" (Ghidra, IDA, objdump, Rizin): REA nunca instala software não relacionado | Já alinhado: `doctor` só informa |
| Contratos e esquemas validados, erros tipados, catálogo de ferramentas completo | A fazer: erros tipados (`ErrNotFound`, `ErrTimeout`…) em vez de strings |
| Regras de ouro do `AGENTS.md`: preservar identidade e incerteza entre camadas; não ampliar escopo por robustez teórica | Adotadas neste documento |

## Pontos de partida dentro do REA para estudar a fundo
- `docs/architecture.mermaid`: camadas (domínio, contratos, provedores, aplicação, CLI/MCP).
- `docs/tool-design.md`: formas de ferramenta (`inspect`, `search`, `trace`, `compare`, `workflow`).
- `docs/mcp-contracts.md`: formato de resultado e identidade de evidência.
- `src/ghidra/` e `bridge/ghidra/ReaGhidraBridge.java` (5 mil linhas): como a ponte funciona.
- `src/process/`: supervisão de processos.
- `src/rizin/` e `src/objdump/`: perfis de comando prontos, úteis como lista de comandos.
- `docs/ghidra-mips.md`, `ghidra-psp.md`: MIPS no Ghidra; o PSP é parente próximo do PS1.

## Licença
O REA é MIT: permite estudar, reutilizar e modificar, com a nota de copyright mantida em trechos copiados.
Preferimos reimplementar ideias em Go. Se algum trecho for copiado, manter o aviso da licença e registrar a origem.
Terceiros listados em `THIRD_PARTY_NOTICES.md` têm licenças próprias.
