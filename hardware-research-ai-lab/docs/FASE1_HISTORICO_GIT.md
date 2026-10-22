# Fase 1 — Histórico Git e evidências

## Fluxo
1. `hrail research verificar --online --clonar` — por fonte: `git ls-remote HEAD` (existência), clone raso parcial
   (`--depth`, `--filter=blob:none`, `--no-checkout`) para data e hash do último commit, e leitura do arquivo de licença
   (apenas texto). Sites: `HEAD` HTTP. Resultado em `source_verifications`; **o catálogo JSON não é alterado**
   (`research sources` sobrepõe o resultado). Status: `verificado`, `parcial`, `inacessivel` (continua `nao_verificado`).
2. `hrail research historico --fonte ID --palavras a,b` — `git log` somente leitura; grava em `commit_findings`
   (hash, data, assunto, reversão e commit revertido, palavras-chave, referências `#N`/`!N`/URLs). **Autores não são coletados.**
3. `hrail research commits` — consulta achados.
4. `hrail research evidencia ...` — uma **pessoa** decide a postura (`favoravel|contraria`); o commit precisa constar nos achados;
   a URL (`.../commit/<hash>`) é montada pelo HRAIL. Atualiza o estado de evidência do experimento.

## Segurança
- Rede só com `--online` explícito; nada é baixado em outros comandos.
- Sem checkout: nenhum arquivo do repositório vai para o disco como arquivo executável; hooks/fsmonitor/transporte `ext` desativados
  (teste: hooks e `core.fsmonitor` maliciosos não executam).
- `verificado` significa "existe, responde e tem histórico coerente". **Dono oficial/autenticidade institucional não são confirmados
  automaticamente** (a nota de cada fonte avisa). Licença divergente do catálogo é sinalizada, não corrigida.

## Limites conhecidos
- Profundidade padrão 200 (use `--profundidade`): histórico anterior fica fora da análise.
- Palavra-chave é busca por substring (`gfx8` casa `gfx803`) em assunto e corpo.
- Reversão = corpo iniciado por "This reverts commit" ou assunto "Revert…" (com prefixo `área:`). Heurística: confira o commit.
- Issues referenciadas não são baixadas (sem API/token); só o texto da referência é guardado.
- "Sem achados" ≠ compatível nem incompatível.
