# Arquitetura: Fábrica Local de Aplicativos por IA

Documento de arquitetura do Lumivox como "fábrica local de aplicativos":
um ambiente que recebe uma descrição do que deve ser criado, ou um ZIP
de um projeto incompleto, analisa, planeja, edita código, executa
testes, corrige erros e produz o programa final — tudo local, sem
depender de nuvem para a inferência de IA.

Complementa `PESQUISA_FERRAMENTAS_UIUX_OPENSOURCE.md` (ferramentas de
wireframe/UI-UX) e `motor_ia/` (seletor automático de motor de IA).

## 1. Visão geral

```
                    FÁBRICA LOCAL DE APLICATIVOS
                             │
            ┌────────────────┴─────────────────┐
            │                                   │
      NOVO APLICATIVO                     ABRIR PROJETO
      por descrição                         ZIP/pasta
            │                                   │
            └────────────────┬──────────────────┘
                             ▼
                    ANALISADOR DO PROJETO
                             │
                  ┌──────────┼──────────┐
                  ▼          ▼          ▼
               Código     Recursos   Dependências
                  │          │          │
                  └──────────┼──────────┘
                             ▼
                     PLANEJADOR IA
                             │
                "o que existe / o que falta"
                             │
           ┌─────────────────┼──────────────────┐
           ▼                 ▼                  ▼
       Wireframe           UI/UX           Arquitetura
           │                 │                  │
           └─────────────────┼──────────────────┘
                             ▼
                       AGENTE CODER
                             │
              criar / editar / refatorar
                             │
                             ▼
                      EXECUÇÃO ISOLADA
                             │
                  ┌──────────┼──────────┐
                  ▼          ▼          ▼
               Build       Testes     Linter
                  │          │          │
                  └──────────┼──────────┘
                             ▼
                   IA ANALISA OS ERROS
                             │
                        CORRIGE
                             │
                        TESTA NOVO
                             │
                      até passar gates
                             ▼
                    APLICATIVO FINAL
                 Windows / Linux / Web
                       / Android
```

## 2. Modo "Terminar projeto"

Fluxo de valor mais alto: o usuário entrega um `meu_programa.zip` e recebe
um diagnóstico objetivo antes de qualquer alteração:

```
Projeto detectado
────────────────────────
Python/PySide6
87 arquivos
GUI existente
SQLite existente
23 TODOs
6 funções incompletas
2 módulos sem implementação
11 testes falhando
dependência ausente: ...
build Windows incompleto

Estado estimado: 72%

[ Analisar ]
[ Propor conclusão ]
[ Corrigir automaticamente ]
```

A IA trabalha por etapas, com checkpoint antes de cada alteração, diff
dos arquivos e possibilidade de rollback.

## 3. Segurança: ZIP nunca é executado diretamente

Um projeto recebido pode conter `install.sh`, `setup.py`, scripts de
`package.json`, `Makefile`, `.exe`, DLL, PowerShell ou algo malicioso.
Fluxo obrigatório:

```
ZIP
 ↓
EXTRAÇÃO SEGURA
 ↓
LEITURA ESTÁTICA
 ↓
INVENTÁRIO
 ↓
SCAN
 ↓
SNAPSHOT
 ↓
SANDBOX
 ↓
só então BUILD/TEST
```

Nenhuma etapa de build/test roda fora da sandbox (sem rede, sem acesso
ao resto do disco, limites de CPU/tempo). Isso precisa existir **antes**
de qualquer capacidade de "corrigir automaticamente" — do contrário o
modo "Terminar projeto" vira a maior superfície de ataque do programa.

Implementado neste repositório:

- `importador_zip/`: extração segura (bloqueia zip-slip, symlinks e zip
  bombs), inventário, scan heurístico de padrões perigosos e snapshot
  com hash por arquivo. Devolve `pode_auto_prosseguir`.
- `sandbox_execucao/`: executa build/test isolado via `bubblewrap`
  (sem rede por padrão, escrita confinada ao diretório do projeto,
  timeout e limite de memória). Recusa rodar se o relatório do
  `importador_zip` não liberou o projeto, a menos que um humano
  revise e libere explicitamente.

Os dois módulos foram testados de ponta a ponta, inclusive com um ZIP
malicioso de zip-slip (rejeitado antes de tocar o disco) e um comando
tentando acessar rede/escrever fora de `/work` dentro do sandbox
(ambos bloqueados).

## 4. Agentes especializados

Em vez de um único agente tentando fazer tudo:

```
ORQUESTRADOR
    │
    ├── Arquiteto
    ├── Analista de ZIP
    ├── UI/UX Designer
    ├── Programador
    ├── Dependency Agent
    ├── Debugger
    ├── Test Engineer
    ├── Accessibility Agent
    ├── Security Reviewer
    └── Release Builder
```

Vários desses papéis se sobrepõem a conceitos já usados no ecossistema
LVCP (Dependency Oracle, Accessibility Forge, Runtime Bridge, Toolchain
Forge, Update Forge, Session Guardian) — não é preciso partir do zero.

## 5. Motor de IA: camada única, motor plugável

O orquestrador nunca fala diretamente com um motor específico. Ele
consulta `motor_ia/selecionar_motor.py`, que detecta hardware e motores
em execução e devolve um `base_url` compatível com a API da OpenAI.

```
              MOTOR LOCAL DE IA

        ┌──────────────┴──────────────┐
        │                             │
 llama.cpp + Vulkan              Conectores
    PADRÃO                          opcionais
        │                  ┌──────────┴─────────┐
        │                  ▼                    ▼
      GGUF              Ollama              LM Studio
                         API                   API
```

- **llama.cpp + Vulkan**: motor padrão. Não depende de AVX2, funciona
  bem em GPUs mais antigas via driver RADV/Mesa.
- **Ollama**: opção futura/paralela. Roda em qualquer CPU; backend
  Vulkan para GPU AMD/Intel ainda experimental (2026).
- **LM Studio**: opção futura. Exige AVX2 em Linux/Windows x64.

A seleção é automática por capacidade de hardware + disponibilidade do
servidor, não fixada no código — ver `motor_ia/README.md` para detalhes
e como estender.

## 6. Perfil de hardware de referência

Recomendação concreta para a máquina de desenvolvimento atual: **Xeon
(plataforma X79, sem AVX2, memória quad channel) + RX 580 8GB + NVMe
500GB + Ubuntu**.

### 6.1 Motor de IA nesta máquina

- **llama.cpp + Vulkan (RADV/Mesa) é o motor correto.** ROCm está fora:
  a AMD parou de compilar suporte a gfx803 (Polaris/RX 580) a partir do
  ROCm 6.0, e o ROCm 7 rejeita o card na criação do agente HSA — só
  sobrevive via patches de comunidade frágeis, não é caminho de
  produção.
- O driver RADV do Mesa tem suporte maduro a Polaris; o backend Vulkan
  do llama.cpp contorna o ROCm inteiramente. Existe um bug conhecido
  (`VK_ERROR_DEVICE_LOST` em `vkCreateDevice`) em builds recentes com
  Polaris — resolvido compilando da fonte com `GGML_VULKAN=ON` usando
  Vulkan SDK ≥1.4.341.1, ou usando um fork já ajustado para RX 580.
  Desempenho real reportado nessa GPU: ~6-18 tok/s conforme modelo e
  quantização.
- **LM Studio fica fora hoje**: exige AVX2, que este Xeon (Sandy/Ivy
  Bridge-E) não tem.
- **Ollama fica como opção secundária/API**: suporte Vulkan ainda
  experimental desde a 0.12.6 (2026), instável para uso pesado.

### 6.2 Escolha de modelo: aproveitando o quad channel

Com 8GB de VRAM isolados, o caminho óbvio é um denso 7B-8B em Q4_K_M
(cabe inteiro na GPU, ~4-5GB). Mas a memória **quad channel** do X79
abre uma segunda opção: já há relato de RX 580 8GB rodando um **MoE de
35B via Vulkan em fit híbrido** GPU+CPU, porque em MoE só os experts
ativos por token entram no cálculo — a banda de quad channel é
exatamente o que sustenta a parte que cai na RAM.

- **Perfil rápido/leve**: denso 7-8B (Qwen2.5-Coder-7B,
  DeepSeek-Coder-6.7B) Q4_K_M, 100% na GPU — iterações curtas do agente.
- **Perfil raciocínio pesado**: MoE maior (classe 30-35B) com offload
  híbrido GPU+CPU — planejamento/arquitetura do orquestrador, mesmo sem
  AVX2.
- Popular **todos os canais de RAM com pentes idênticos** (mesma
  capacidade/velocidade) é o que garante o ganho de banda no fit
  híbrido. Mais RAM (32-64GB+) permite MoE maiores.

### 6.3 Edição do aplicativo e orçamento de disco (NVMe 500GB)

Começar na edição **Developer** (5-12GB), não Full Studio — o NVMe
precisa sobrar espaço para modelos e projetos do usuário:

| Item | Estimativa |
|---|---|
| Ubuntu + pacotes base | 20-30 GB |
| App (Developer edition) | ~10 GB |
| 1 modelo denso 7-8B + 1 MoE ~30B (GGUF) | ~20-25 GB |
| Toolchains extras (Java/.NET/Flutter/Android) | sob demanda, opcional |
| Projetos do usuário + build/cache | resto (~400 GB+) |

Edições de referência:

| Edição | Conteúdo | Espaço alvo |
|---|---|---|
| Core | editor + IA externa + análise ZIP | 1–3 GB |
| Developer | Core + Python/Node/Git/build básico | 5–12 GB |
| Full Studio | compiladores + Web + Desktop + Android | 25–60+ GB |

### 6.4 Setup no Ubuntu

```bash
sudo apt install mesa-vulkan-drivers vulkan-tools
vulkaninfo | grep "deviceName"   # confirma que a GPU aparece via RADV
```

Se `vulkaninfo` não listar a GPU, o kernel `amdgpu` já vem embutido em
kernels recentes do Ubuntu — não é necessário driver proprietário AMD.

## 7. Diretriz de design: visual minimalista

Princípio de produto para toda a interface do Lumivox (editor,
orquestrador, telas de diagnóstico de projeto, designer de UI/UX):
**visual minimalista** — hierarquia visual clara, poucas cores,
elementos essenciais visíveis, sem ornamentação. Isso vale tanto para
as telas do próprio aplicativo quanto para os wireframes/UI gerados
para os projetos dos usuários (ver `PESQUISA_FERRAMENTAS_UIUX_OPENSOURCE.md`).

## 8. Escopo ainda não coberto

Wireframe, UI/UX, protótipo, teste de usabilidade e o motor de IA local
resolvem uma fatia importante, mas não fecham o ciclo completo:

```
IDEIA
  ↓
REQUISITOS
  ↓
┌──────────────────────────────┐
│ WIREFRAME              │ ← Excalidraw / WireMD
│ USER FLOW              │ ← draw.io
│ UI/UX                  │ ← Penpot
│ PROTÓTIPO              │ ← Penpot
│ TESTE DE USABILIDADE   │ ← Quant-UX
│ MOTOR DE IA LOCAL      │ ← motor_ia/ (este repositório)
│ IMPORTAÇÃO SEGURA DE ZIP│ ← importador_zip/ (este repositório)
│ SANDBOX DE EXECUÇÃO    │ ← sandbox_execucao/ (este repositório)
└──────────────────────────────┘
  ↓
DESENVOLVIMENTO REAL      ← agente Coder ainda precisa pesquisar/construir
  ↓
BACKEND / BANCO / APIs    ← ainda precisa pesquisar
  ↓
TESTES                    ← execução isolada existe; runner de testes por linguagem ainda precisa pesquisar
  ↓
ACESSIBILIDADE            ← precisa camada própria
  ↓
BUILD / INSTALADOR        ← ainda precisa pesquisar
  ↓
ATUALIZAÇÃO / RELEASE     ← ainda precisa pesquisar
```

## 9. Próximos passos

1. **Product/Requirements Engine** — requisitos, histórias, casos de uso e arquitetura.
2. **Code Builder Engine** — transformar telas/componentes em código real.
3. **Backend Builder** — APIs, banco de dados, autenticação e armazenamento.
4. **Accessibility Engine** — WCAG, teclado, leitor de tela, contraste, CAA, Braille etc.
5. **QA/Test Engine** — testes unitários, integração, GUI e acessibilidade.
6. **Build & Release Engine** — Windows, Linux, Android, instalador, atualização e assinatura.

Cada camada nova deve seguir o mesmo princípio do motor de IA: interface
plugável, sem acoplar o orquestrador a uma ferramenta específica.
