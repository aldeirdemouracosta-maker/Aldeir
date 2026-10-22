# Fase 2 — Integração inicial do MGPUSim

## Fluxo (cada etapa só avança com a anterior)
```
research verificar --online --clonar   (Fase 1: clone raso em data/clones/mgpusim)
simulation preparar     extrai o commit FIXADO (git archive, sem .git/hooks) em data/_sim/mgpusim/src
simulation revisar      go list -deps: imports sensíveis, módulos, replace; grava a revisão (impressão digital)
simulation aprovar      APROVAÇÃO HUMANA (--commit completo, --por "nome"); vale só para esta impressão digital
simulation compilar     go build isolado (GOPATH/GOMODCACHE/GOCACHE em data/_sim; go.sum verificado; -mod=readonly)
simulation rodar        executa no sandbox, extrai métricas, grava resultados origin=simulated
simulation resultados   lista resultados simulados
```
`compilar` e `rodar` exigem também `--autorizo-codigo-terceiros`.

## Controles de segurança (testados)
- **Versão fixa:** `catalog/simulators.json` fixa o commit (40 hex). Mudar commit, `go.mod`, `go.sum`, flags fixas ou amostra muda a impressão digital → nova revisão e nova aprovação.
- **Sem flags livres:** os argumentos são montados pelo HRAIL a partir de valores numéricos limitados (`length` ≤ 65536, `taps` ≤ 256). Flags de trace, monitor, daisen, `-debug-isa` etc. são recusadas no catálogo.
- **`-disable-rtm` obrigatório:** o portal AkitaRTM (servidor HTTP) é ligado por padrão no simulador.
- **Sandbox de execução:** diretório descartável por execução, **ambiente limpo** (só `PATH` e `HOME`; variáveis do usuário não vazam), **rede isolada** (`unshare -n`; recusa rodar sem isolamento salvo `--permitir-sem-isolamento`), timeout (padrão 2 min, máx. 10), saída limitada, grupo de processos encerrado no timeout.
- **Integridade do binário:** `sha256` registrado na compilação e conferido antes de cada execução; binário alterado é recusado.
- **Extração segura:** `tar` sem symlinks/hardlinks, caminhos fora do destino recusados.
- **Resultados:** `origin=simulated`, experimento marcado como teste de infraestrutura ⇒ `ClaimImprovement` os recusa por construção.
- **Limites do sandbox:** não há limite de memória/CPU (apenas timeout); o isolamento de rede depende de `unshare` (usuários sem privilégio podem precisar de user namespaces).

## O que o modelo cobre (verificado no código do commit fixado)
- ISA **GCN3** (emulação funcional + temporização) estilo **AMD R9 Nano**: padrão `gpu=r9nano`, `arch=gcn3`.
- Configuração padrão lida do código: **1 GHz, 16 shader arrays × 4 CUs = 64 CUs, L2 de 2 MB, 16 bancos de memória, DRAM de 4 GB.**
- Métricas por CU/SIMD: contagem de instruções, CPI, pilhas de CPI, tempo de kernel, caches/TLB, transações de memória.
- Verificação funcional opcional (`-verify`), determinismo (mesmo `kernel_time` em execuções repetidas).

## O que NÃO cobre / não foi estabelecido
- **Não é a RX 580 2048SP.** O modelo padrão é R9 Nano (Fiji, HBM, 64 CUs). A RX 580 2048SP é Polaris (GCN4), memória GDDR5; o nome sugere 2048 stream processors (≈ 32 CUs de 64 SPs — **inferência, não medido**). Clocks, caches, largura/latência de memória e CUs da placa real **não foram calibrados**.
- **GCN3 ≢ Polaris:** há pista de compatibilidade de ISA (o MGPUSim usa kernels `gfx803`, e toolchains tratam a Polaris como gfx803), mas **nenhuma equivalência de microarquitetura/temporização foi demonstrada**. `ClaimEquivalence` continua recusando.
- Resultado simulado **não é desempenho esperado** da RX 580; só a Fase 5 (calibração com medições) pode relacioná-los.
- Só a amostra `fir` está habilitada; outras exigem revisar flags e adicionar ao catálogo.
- Revisão de código é **por padrões e leitura parcial**, não auditoria.
