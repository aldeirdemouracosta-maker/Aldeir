# PS5 × RX 580: limitações

> Conhecimento geral, **não verificado nesta sessão** (sem acesso de rede). Confirmar em fontes primárias antes de citar.

1. **Arquiteturas diferentes.** A RX 580 é Polaris (GCN 4). A GPU do PS5 é amplamente documentada como derivada de RDNA 2.
   Nenhum resultado, shader, otimização ou comportamento de driver deve ser transferido de uma para outra sem evidência.
2. **Equivalência GCN3 / Polaris / gfx9 não estabelecida.** O MGPUSim modela GCN3 (segundo o projeto). O HRAIL recusa
   (`simulation.ClaimEquivalence`) qualquer alegação de equivalência sem evidência, e mesmo com evidência a registra apenas
   como `alegada_nao_validada`.
3. **RX 580 2048SP ≠ RX 580 convencional.** PCI ID esperado `1002:6fdf` (tabela interna, **inferido**). Contagem de shaders,
   clocks, limites Vulkan e compatibilidade devem ser verificados na máquina real. O perfil marca `requer_verificacao`.
4. **Repositório PS5_Vulkan não verificado.** Origem, licença, conteúdo e legalidade não foram avaliados. Regras: não executar
   código, não usar chaves, firmware ou material proprietário obtido indevidamente, só documentação pública.
5. **Sem execução na Fase 0.** Nenhum código de GPU, driver ou firmware é executado; qualquer experimento C+ está desativado.
6. **Simulação ≠ medição.** Resultados simulados/estimados nunca sustentam alegação de melhoria.
