# REA Studio Multi-IA — Fase 0 / MVP

Aplicativo WPF (.NET 10) para REA, Ghidra e múltiplos provedores de IA, com fallback automático para Ollama.
**Status: código escrito sem compilador disponível — ainda NÃO compilado e NÃO testado.** Veja `docs/`.

## Iniciar (no Windows, com .NET 10 SDK)
```
cd REA-Studio
dotnet test tests/ReaStudio.Tests
dotnet run --project src/ReaStudio.App
```

## O que funciona de fato (por design, a validar no 1º build)
Detecção de modelos Ollama reais, chat com Ollama, roteamento Manual/Automático/Somente local com checkpoint,
adaptadores HTTP OpenAI/Anthropic (com chave via DPAPI), diagnóstico, detecção PE/ELF, cliente MCP.
Tudo o que aparece desabilitado na UI não está implementado (BUTTON_EXISTS != BUTTON_WORKS).

## Backup GitHub privado
Crie um repositório **privado** vazio e: `git remote add backup <url> && git push backup <branch>`.
