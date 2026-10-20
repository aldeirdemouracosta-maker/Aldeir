# Compatibilidade Pascal
Candidato conservador: Python 3.12 + torch 2.7.1 cu126. A wheel oficial existe para Windows/Linux. Validar arquitetura da wheel instalada e operacao real; documentacao nao equivale a teste na P100.
https://pytorch.org/get-started/previous-versions/
https://github.com/pytorch/pytorch/blob/v2.7.1/RELEASE.md
CUDA 12.6 GA: driver associado Windows >=560.76 / Linux >=560.28.03. Compatibilidade minor CUDA 12.x admite Windows >=528.33 / Linux >=525.60.13 com limitacoes; nao confundir com driver associado. Driver local 341.74 insuficiente. Nenhuma alteracao automatica.
https://docs.nvidia.com/cuda/archive/12.6.0/cuda-toolkit-release-notes/index.html
Toolkit local nao e necessario para executar wheel PyTorch; sera necessario para compilar kernels CGO/CUDA.
Nao usar CUDA 13, BF16, FlashAttention-2. Treinamento futuro FP16, eager e gradient checkpointing.
bitsandbytes e opcional: documentacao lista sm60 nos builds CUDA 11.8–12.6 Windows/Linux x64. Confirmar versao instalada e NF4 real antes de QLoRA; ainda nao validado.
https://huggingface.co/docs/bitsandbytes/main/en/installation
