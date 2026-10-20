# Regras do projeto
Go como linguagem principal. Python somente ML e ferramentas.
Prioridade Tesla P100 16 GB sm_60, CUDA 12.x; nunca CUDA 13 para Pascal.
Nao alterar drivers, apagar arquivos, sobrescrever modelos ou publicar remotamente.
Nao iniciar treinamento sem teste CUDA real aprovado e autorizacao da fase correspondente.
Nao usar BF16, FlashAttention-2 ou kernels exclusivos de Tensor Cores.
Registrar testes reais, erros e limitacoes. Preservar fallback CPU.
