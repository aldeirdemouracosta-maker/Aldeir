# Segurança

| Regra | Aplicação |
|---|---|
| Somente leitura por padrão | discos do host nunca montados automaticamente; quando necessário, `mount -o ro,noexec,nosuid,nodev`; blockdev `--setro` no dispositivo |
| Nunca gravar firmware | sem ferramentas de gravação (flashrom, fwupd) na ISO; Guardian bloqueia comandos conhecidos; módulos não podem declarar essa permissão |
| Nunca executar amostras desconhecidas | análise estática; qualquer execução só em VM descartável opcional (módulo externo, fase futura), nunca no host live |
| Não alterar partições do computador no boot | sem instalador, sem `fsck`/`growpart`, `noswap` (swap do host não é ativada); teste de aceite: hash dos primeiros setores/tabela de partições do disco interno antes e depois do boot no QEMU |
| Downloads somente com autorização | diálogo mostra URL, tamanho e destino; arquivo vai a quarentena sem permissão de execução; SHA-256 registrado; sem rede por padrão |
| Relatórios | SHA-256 de cada entrada/saída, linha do tempo, versões das ferramentas (hash do módulo), motor de IA e modelo usados em cada resultado, e proveniência (origem, data, quem autorizou) |
| Modo Oficina | separado, banner permanente; cria **cópia de trabalho** com hash do original; o original permanece ro e é reverificado; nunca opera em dispositivo bruto |
| Segredos | chaves de API nunca em logs nem relatórios; sem extração de tokens de outros programas |
| Entrada hostil | arquivos tratados como dados: limites de tamanho/profundidade (zip-bomb), bloqueio de path traversal, sem abrir macros, sem seguir symlinks para fora |
| Processos | serviços como usuário sem privilégio; sudo restrito a montagem ro; sem escuta em rede |

Limitação honesta: modo "somente leitura" por software não substitui bloqueador de escrita em hardware para perícia formal.
