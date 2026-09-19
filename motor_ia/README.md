# Motor de IA local — seleção automática

Camada única de abstração entre o orquestrador do Lumivox e o motor de
inferência local. O orquestrador nunca fala diretamente com llama.cpp,
Ollama ou LM Studio — ele consulta `selecionar_motor.py`, recebe um
`base_url` compatível com a API da OpenAI e usa esse endpoint.

## Por quê

Nem todo motor roda em qualquer hardware:

- **LM Studio** exige AVX2 no Linux/Windows x64.
- **Ollama** roda em qualquer CPU, mas seu backend Vulkan para GPUs
  AMD/Intel ainda é experimental (desde a 0.12.6, 2026).
- **llama.cpp** compilado com backend Vulkan (`GGML_VULKAN=ON`) não
  depende de AVX2 e funciona bem em GPUs mais antigas (ex.: RX 580 via
  driver RADV/Mesa), sendo por isso o motor padrão neste ambiente.

Em vez de fixar um motor no código, `selecionar_motor.py` detecta em
tempo de execução:

1. Se a CPU tem AVX2 (`/proc/cpuinfo`).
2. Se há um driver Vulkan funcional (`vulkaninfo --summary`).
3. Se algum dos servidores locais (`:1234` LM Studio, `:11434` Ollama,
   `:8080` llama.cpp) está de pé e respondendo.

E devolve o primeiro motor, na ordem de prioridade definida em
`motores_conhecidos()`, que for **elegível pelo hardware** e estiver
**respondendo**.

## Efeito de um upgrade futuro

Hoje (Xeon sem AVX2 + RX 580), LM Studio fica automaticamente inelegível
e o llama.cpp via Vulkan é escolhido. Se a máquina ganhar uma CPU com
AVX2 e o usuário instalar/rodar o LM Studio, a próxima chamada a
`selecionar_motor()` passa a escolhê-lo sozinha — nenhuma linha do
orquestrador precisa mudar.

## Uso

```bash
python3 selecionar_motor.py
```

Saída (exemplo):

```json
{
  "escolhido": "llama.cpp (Vulkan)",
  "base_url": "http://localhost:8080/v1",
  "diagnostico": [ ... ]
}
```

Como biblioteca:

```python
from motor_ia.selecionar_motor import selecionar_motor

resultado = selecionar_motor()
if resultado["escolhido"] is None:
    raise RuntimeError(resultado["mensagem"])

base_url = resultado["base_url"]  # usar como endpoint OpenAI-compatible
```

## Extensão

Para adicionar um novo motor (ou ajustar prioridade/portas), edite a
lista retornada por `motores_conhecidos()` em `selecionar_motor.py`.
Cada entrada é um `MotorIA` com:

- `requisito_hardware`: função que retorna `True`/`False` (checagem de
  CPU, GPU, etc.).
- `verificar_disponivel`: função que confirma se o servidor está de pé.

Nenhuma outra parte do código precisa saber como cada motor funciona
por dentro.

## Segurança de GPU

Três funções, sem dependência nova (Linux, lendo `/proc` e `/sys`),
existem por causa de um incidente real: um `llama-server` sem limite
de camadas na GPU sob carga sustentada travou o driver Vulkan de uma
RX 580 até corromper o sistema (ver `TESTE_LOCAL.md`). O orquestrador
já usa `-ngl`/`--ctx-size` conservadores em tudo que ele mesmo sobe
(`busca_codigo`, `visao_mockup`) — estas três funções cobrem o que ele
**não controla**: um `llama-server` de código subido manualmente pelo
usuário fora do seu processo.

- `listar_processos_llama_server()` — lista todo processo
  `llama-server` rodando agora (lendo `/proc/<pid>/cmdline`) e se cada
  um foi iniciado com `-ngl`/`--n-gpu-layers`. Só informa, não age.
- `encerrar_processos_llama_server()` — manda `SIGTERM` em todo
  processo listado acima. Botão de emergência: complementa a função
  anterior com uma forma de agir sobre o aviso sem precisar achar o
  PID na mão. Aceita `matar` (padrão `os.kill`) pra ser testável sem
  matar processo de verdade.
- `temperatura_gpu_celsius()` — lê a maior temperatura entre as GPUs
  via sysfs (`/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input`).
  Devolve `None` se não achar sensor (fora do Linux, sem GPU dedicada,
  hwmon ainda não populado) — quem chama decide o que fazer com a
  ausência de leitura. `busca_codigo.buscar_codigo` e
  `visao_mockup.interpretar_mockup` usam isso pra **recusar** subir um
  `llama-server` na GPU se ela já estiver acima de
  `LIMITE_TEMPERATURA_GPU_CELSIUS` (90°C por padrão) — checagem
  adicional ao limite de camadas: não adianta limitar `-ngl` se a
  placa já estava no limite antes mesmo de começar.

Todas as três são usadas pela interface (botões "Verificar
configuração da GPU" e "Encerrar todos os llama-server" — ver
`interface/README.md`).
