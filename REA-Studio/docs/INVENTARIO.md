# Inventário do ambiente (Fase 0)

Executado na sessão de desenvolvimento em nuvem (Linux), **não** na máquina Windows do usuário.

| Item | Resultado |
|---|---|
| SO da sessão | Linux (não Windows); `C:\Projetos\REA-Studio` inexistente aqui |
| .NET SDK | **ausente**; download bloqueado pelo proxy da sessão (`builds.dotnet.microsoft.com`) |
| Ollama | ausente / sem resposta em `127.0.0.1:11434` |
| REA, Ghidra, Codex, `C:\Projetos\REA-Laboratorio` | inacessíveis nesta sessão; **nada foi lido nem modificado** |
| Repositório | `aldeirdemouracosta-maker/Aldeir` (contém projeto Android não relacionado) |

Consequência: o código foi escrito sem compilador. **Nenhum build e nenhum teste foram executados.**
O inventário real de REA/Ghidra/Ollama deve ser feito na máquina do usuário pelo botão *Diagnóstico* do app.

O código está em `REA-Studio/` dentro do repositório. Para o destino previsto, copie a pasta para `C:\Projetos\REA-Studio`.
