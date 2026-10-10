---
name: aether-investigar-projeto
description: "Investiga arquitetura, dependências e comandos com fatos rastreáveis antes de propor mudanças."
---

# Investigar projeto

1. Leia as instruções do projeto, documentação e arquivos de configuração existentes.
2. Liste os módulos e pontos de entrada. Identifique dependências, versões declaradas,
   persistência, integrações e comandos de execução, teste e análise disponíveis.
3. Localize o código relacionado ao objetivo por leitura ou busca. Cite arquivos,
   símbolos e intervalos de linhas efetivamente observados.
4. Separe FATOS OBSERVADOS de HIPÓTESES. Não deduza que um comando funciona só
   porque aparece na documentação. Marque o que precisa de reprodução ou execução.
5. Mostre um plano curto antes de alterar arquivos. Pergunte ao usuário quando
   faltar uma decisão que mude o resultado esperado.
6. Entregue mapa conciso da arquitetura, caminhos relevantes, comandos encontrados
   e lacunas. Preserve recursos e mudanças existentes.

Esta habilidade não habilita terminal, rede ou novas ferramentas. Se uma
dependência não estiver disponível, registre BLOCKED em vez de inventar resultados.
