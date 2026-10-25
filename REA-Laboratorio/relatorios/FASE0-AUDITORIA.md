# REA-Laboratorio OS — Fase 0 — Auditoria

**Escopo real:** a sessão que produziu este relatório roda em **Linux (Ubuntu 24.04, nuvem)**. O diretório
`C:\Projetos\REA-Laboratorio` **não é acessível** daqui. Portanto **o projeto existente não foi auditado**: nenhum arquivo,
script, configuração do REA ou fase anterior foi lido, alterado ou apagado. Nada foi instalado.

## 1. Resultado dos comandos nesta sessão (ambiente de nuvem, NÃO a sua máquina)
| Item | Resultado |
|---|---|
| Listagem do projeto | impossível: caminho inexistente na sessão |
| Git | 2.43.0 (presente) |
| Node.js | v22.22.0 (presente) |
| Python | 3.13.17 (presente) |
| Java | presente (versão não relevante: é a JVM da sessão) |
| WSL2 | ausente (sessão é Linux nativo) |
| QEMU | **ausente** |
| Ghidra | **ausente** |
| `codex mcp get rea` | **não executado**: Codex ausente (`~/.codex` inexistente) |
| Ferramentas de ISO (`xorriso`, `mksquashfs`, `lb`, `debootstrap`, `grub-mkrescue`, `apk`) | todas ausentes |
| Firmware UEFI da sessão | não (`/sys/firmware/efi` inexistente) |

Consequência: **não é possível compilar nem testar ISO nesta sessão.** Nenhuma ISO existe.

## 2. Como obter a auditoria real (somente leitura)
Na raiz do projeto, no Windows:
```
powershell -ExecutionPolicy Bypass -File scripts\auditar-ambiente.ps1
```
Gera `relatorios\AUDITORIA-LOCAL-<data>.md` (arquivo novo; nada é alterado) com: árvore do projeto, versões de Git/Node/
Python/Java/WSL2/QEMU/Codex, `codex mcp get rea`, busca da instalação do Ghidra e lista de scripts/documentos das fases
anteriores. **Pendente:** executar e revisar o resultado; só então preencher abaixo.

## 3. O que já funciona / o que está pendente
| Item | Estado | Evidência |
|---|---|---|
| Projeto REA-Laboratorio (fases anteriores) | **DESCONHECIDO** | não acessível nesta sessão |
| Configuração MCP `rea` | **DESCONHECIDA** | `codex mcp get rea` não executado |
| Ferramentas do host (QEMU, WSL2, Ghidra) | **DESCONHECIDAS** | script acima |
| Documentação da Fase 0 (`docs/*.md`) | **criada** (rascunho para revisão) | este commit |
| Script de auditoria | **escrito, não executado** | `scripts/auditar-ambiente.ps1` |
| Esqueleto de build | **escrito, não executado, não validado** | `scripts/build-iso.sh` |
| ISO | **não existe** | — |

Relacionado (outro projeto, mesma sessão): `REA-Studio/` (app WPF multi-IA) tem leitor somente-leitura de registro MCP
e AI Bridge em C#; **não compilado**. Pode inspirar o REA AI Bridge, mas é código distinto.

## 4. Bloqueios
1. Sessão sem acesso ao projeto/Windows → auditoria real depende de você rodar o script.
2. Sem QEMU/ferramentas de ISO aqui → build e testes de boot só em host próprio (Debian/WSL2/VM).
3. Push ao GitHub indisponível (sem credencial); o remoto desta sessão é o repositório `Aldeir`, não o do REA-Laboratorio.

## 5. Próxima ação técnica
Rodar o script de auditoria, anexar o relatório, e executar o Gate G1 de `docs/BUILD-ISO.md` (build mínimo + boot BIOS/UEFI
no QEMU + medição de tamanho).
