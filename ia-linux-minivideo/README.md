# IA-Linux MiniVideo

Ambiente Linux dedicado à criação, edição e melhoria de vídeo e áudio com IA
local. Separado do Mini IA Local, da Fábrica - App e do Avalia Matemática. O
editor mantém o comando `mini-ia-videos` por compatibilidade.

> **Estado em 2026-09-24:** o código do editor `mini-ia-videos` **não está
> neste repositório** (veja `docs/AUDITORIA.md`). Esta pasta contém, por
> enquanto, as duas peças independentes do editor:
>
> - `minivideo-audit`: auditoria reproduzível e somente leitura da máquina.
> - `minivideo-guard`: Hardware Safety Guard somente leitura, sem root.

## Instalação

```bash
cd ia-linux-minivideo
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'     # sem dependências de execução; pytest só para testes
python -m pytest -q
```

## Auditoria (não altera nada, não usa rede)

```bash
minivideo-audit                               # quadro legível
minivideo-audit --models-dir ~/modelos --json -o auditoria.json
```

Detecta instruções da CPU (AVX/AVX2), RAM, disco, GPUs (sysfs), Vulkan
(`vulkaninfo --summary`), CUDA/VRAM (`nvidia-smi`), ferramentas (FFmpeg,
PySceneDetect, Auto-Editor, whisper.cpp, RIFE, Real-ESRGAN, llama-server,
`mini-ia-videos`), módulos Python e arquivos de pesos. Também lista o que
fica **indisponível** e por quê.

## Hardware Safety Guard

```bash
minivideo-guard detect                 # GPUs e sensores disponíveis/indisponíveis
minivideo-guard sample --json          # uma leitura
minivideo-guard watch --interval 2 --job-id teste   # só observa e registra
minivideo-guard run --job-id job42 --config config/guard-rx580.json -- \
    rife-ncnn-vulkan -i frames/ -o saida/
```

- **Coleta** (`sensors.py`): amdgpu via `/sys/class/drm/cardN/device` e
  hwmon, com temperatura de borda, hotspot e memória, carga, VRAM, potência,
  limite de potência, ventoinha (RPM e %) e clocks. Sensor ausente fica
  `indisponível` e nunca recebe valor inventado. Na Polaris, hotspot e
  temperatura de memória costumam não existir. Há ainda um backend NVIDIA
  (`nvidia-smi`), ainda não validado em hardware.
- **Decisão** (`policy.py`): níveis `normal → atencao → reduzir → pausar →
  critico`. O nível sobe na hora e desce só abaixo do limite menos a
  histerese, depois de N amostras. `critico` fica travado. Os limites vêm de JSON.
- **Ação** (`actions.py`): age sobre o **job**, nunca sobre o hardware. Pede
  redução de carga (se o motor suportar), pausa (SIGSTOP no grupo do
  processo), retoma (SIGCONT) ou encerra (SIGTERM → SIGKILL). **Não altera
  clocks, voltagens, curva de ventoinha nem firmware.**
- **Log:** `guard-logs/<job_id>.guard.jsonl`, com amostras, transições e ações.
- Pausar com SIGSTOP libera a GPU de trabalho novo, mas **mantém a VRAM**.
  Motores integrados devem implementar `JobControl` para pausar entre chunks.

## Documentos

- `docs/AUDITORIA.md`: quadro implementado / configurado / testado / pendente.
- `docs/INTEGRACAO_IA_LINUX_MINIMAL.md`: diagnóstico do boot do kernel e plano.
