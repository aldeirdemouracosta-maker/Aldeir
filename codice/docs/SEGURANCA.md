# Segurança do Códice (estado real)

Feito e testado aqui (testes unitários / `nft -c`):
- Orquestrador: sandbox `bubblewrap` por padrão (só o worktree gravável, HOME/tmp temporários,
  `.git` somente leitura, rede isolada por padrão), falha fechada se `bwrap` faltar; testes do
  módulo também rodam no sandbox sem rede. Chaves só de arquivo `chmod 600`, entregues por módulo.
  A construção do comando bwrap foi testada; **a execução real não** (bwrap indisponível aqui).
- `nftables`: entrada bloqueada, saída livre (regras validadas com `nft -c`).
- `codice-baixar-modelo`: descarta o arquivo se o SHA-256 não confere (testado).

Configurado, NÃO testado (depende da ISO): sysctl de endurecimento, unattended-upgrades
(XanMod fica fora das atualizações automáticas), pre-commit com gitleaks (pacote a confirmar no
trixie), Aether com aprovação de plano ligada, SSH removido, aider sem telemetria.

Limites conhecidos: com `rede: true` o bwrap não filtra destinos; agentes de nuvem veem a rede
inteira. Pendentes: hashes de pip fixados, assinatura da ISO, snapshots/backup, entrada `toram`
no menu de boot (por ora: edite a linha de boot e acrescente `toram`).
