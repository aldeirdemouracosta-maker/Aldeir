# Contexto para o Claude Code — REA Linux

Este kit gera uma ISO Debian 13 mínima para o REA-Laboratorio do Aldeir
(engenharia reversa com IA local). Leia antes de mudar qualquer coisa.

## Hardware alvo
- Xeon 6 núcleos, 32 GB RAM, **RX 580 8 GB** (só IA), **GT 210** (só vídeo), SSD.
- RX 580 (Polaris) não tem ROCm → IA via **Vulkan** (Mesa RADV). `OLLAMA_VULKAN=1`.

## Decisões já validadas no Windows (não desfazer sem motivo)
1. **Ghidra 12.1.4 fixo.** GhidraMCP 2.0 é feito para 12.1.4; o Ghidra recusa extensão de
   outra versão. O 12.2 exige JDK 25. JDK 21 aqui.
2. **GhidraMCP 2.0 pelo release oficial** (zip com extensão + wheel). Nada de compilar.
   O servidor Python é instalado da wheel do mesmo release (`uv tool install "ghidra-mcp[headless] @ file://..."`).
3. **Modelos**: `qwen3-8b-gpu` (qwen3:8b, num_ctx 16384, num_gpu 99) ficou 100% GPU na RX 580;
   `llm4decompile-cpu` (DevQuasar GGUF Q4_K_M, num_gpu 0, TEMPLATE "{{ .Prompt }}") ficou 100% CPU.
   Prompt do LLM4Decompile v2 validado:
   `# This is the assembly code:\n<pseudocódigo>\n# What is the source code?\n` com `raw: true`.
4. **Problema central descoberto: excesso de ferramentas.** O Codex com REA completo + plugins do
   app mandava ~128 mil tokens por pedido; o Ollama cortava para ~8k (`truncating input prompt
   limit=8194 prompt=128267`) e o modelo nunca via as ferramentas do Ghidra.
   Solução: `~/.codex/config.toml` enxuto, com `enabled_tools`:
   - ghidra: 10 ferramentas (lista em `FERRAMENTAS_GHIDRA` no painel)
   - rea: só `binary_session`
   O limite de ~8k também vinha de requisições paralelas → `OLLAMA_NUM_PARALLEL=1`.
5. `rea.binary_session` deve ser chamado **sem argumentos** (`{}`); o modelo pequeno inventou
   `expected_package_version` e a chamada falhou na validação.
6. Codex com modelo local exige o nome com etiqueta: `codex --oss -m qwen3-8b-gpu:latest`.
7. No Windows o npm 12 bloqueou o script de instalação do Frida → `--allow-scripts=frida`.

## Pontos NÃO verificados (testar no primeiro build)
- Nomes de pacotes trixie: `python3-pyside6.*`, `adb`, `apktool`, `polkitd`, `openjdk-21-jdk`.
  (Se PySide6 do apt falhar, apagar `config/package-lists/painel.list.chroot`; o hook 0500 instala via pip.)
- URL do Ollama para Linux (`.tar.zst` com fallback `.tgz`) e se o pacote traz o backend Vulkan.
- Ordem includes.chroot × hooks do live-build (hooks usam `systemctl enable` de unidades das includes;
  falha só gera AVISO, não quebra o build).
- Pasta de configuração do Ghidra no Linux assumida como `~/.config/ghidra/ghidra_12.1.4_PUBLIC`.
- `rea mcp` como comando do servidor REA no Linux (no Windows era `node .../rea.mjs mcp`).
- Ferramentas do GhidraMCP 2.0: nomes tirados de `src/ghidra_mcp/server.py` do repositório
  (tag 2.0, commit 1e98025).

## Arquivos principais
- `build.sh` — build em container `debian:trixie` (precisa `--privileged`).
- `config/hooks/normal/0100..0500` — downloads e ajustes no chroot (precisam de internet).
- `config/includes.chroot/usr/local/lib/rea/painel.py` — painel PySide6; funções puras testáveis
  (`bloco_mcp`, `aplicar_bloco`, `modo_atual`, `cortes_no_log`, `prompt_decomp`).
- `config/includes.chroot/etc/skel/.codex/config.toml` — bloco entre `# >>> rea-painel` e
  `# <<< rea-painel` é reescrito pelo painel (modo janela/headless).

## Pendrive
- Uso principal desejado: rodar do pendrive. `auto/config` inclui `persistence` no boot;
  persistência via Ventoy (arquivo com rótulo `persistence` + `persistence.conf` com `/ union`).
- Painel e `rea-baixar-modelos` detectam persistência por `/run/live/persistence`.

## Próximos passos planejados
- Build e teste em VM (QEMU) → teste na máquina real com RX 580.
- Cliente de agente próprio (mais leve que o Codex) ou OGhidra (github.com/llnl/OGhidra).
- Servidor MCP `refinar_funcao` (Ghidra → LLM4Decompile) para o Codex chamar direto.
