---
name: aether-report-evidence
description: "Produz JSON e resumo de resultados observados, associados à tarefa e ao artefato corretos."
---

# Relatar evidência

Adaptação original de procedimentos inspirados no contrato LVCP. Não representa
uma instalação dessa engine ou resultados de ferramentas externas presumidas.

1. Relate somente observações realizadas nesta tarefa. Identifique a tarefa e o
   artefato; não atribua a outro arquivo, build ou revisão evidências de um estado
   diferente. Informe quando a evidência é insuficiente para a conclusão desejada.
2. Execuções por run_terminal registram comando, código de saída, duração, ambiente,
   fase e limitações. Informe artifact e phase corretos. Não invente esses valores.
3. Para execuções impedidas use record_evidence com motivo e comando previsto.
   O registro será BLOCKED, sem código de saída. Use applicable=false para N/A
   com justificativa. A ferramenta não permite declarar PASS manualmente.
4. Confira o JSON e o resumo legível exportados automaticamente ao fim da tarefa.
   Inclua referências aos registros correspondentes no relatório final.
5. Não copie arquivos de credenciais, variáveis de ambiente completas, tokens ou
   senhas para o relatório. A redação automática é uma proteção adicional e não
   identifica todos os formatos possíveis de segredo.
6. Separe resultado observado, interpretação e limitações. Não declare validação
   humana, cobertura completa ou aprovação sem registro real.

Não faça cache semântico de edições, comandos ou resultados de testes.
