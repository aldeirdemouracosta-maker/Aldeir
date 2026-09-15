# Pesquisa: Ferramentas Open Source de Wireframe e Design de Interface (UI/UX)

Documento de referência do projeto Lumivox, cobrindo os itens **4. Wireframes** e **5. Design de Interface (UI/UX)** da auditoria do aplicativo. A pesquisa foi feita internacionalmente, sem restringir país, sistema operacional ou linguagem de programação, buscando projetos realmente open source que possam servir como referência de conceito, biblioteca integrável ou base arquitetural para um módulo próprio de design.

## 1. Tabela comparativa

| Projeto | Função principal | Plataformas / tecnologia | Licença | Wireframe | UI alta fidelidade | Protótipo | Potencial para o Lumivox |
|---|---|---|---|---|---|---|---|
| [Penpot](https://github.com/penpot/penpot) | UI/UX profissional | Web/self-host; ClojureScript + React + Clojure | MPL-2.0 | ✅ | ⭐⭐⭐⭐⭐ | ✅ | ⭐⭐⭐⭐⭐ |
| [Excalidraw](https://github.com/excalidraw/excalidraw) | Wireframe/sketch | Web/PWA; React + TypeScript | MIT | ⭐⭐⭐⭐⭐ | ⚠️ | ⚠️ | ⭐⭐⭐⭐⭐ |
| [Quant-UX](https://github.com/KaeferM/quantux) | Protótipo + teste UX | Web/Docker; JS + Java | GPL-3.0 | ✅ | ✅ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| [Pencil Project](https://github.com/prikhi/pencil) | Wireframe/mockup | Windows/Linux/macOS; Electron/JS | GPL-2.0 | ⭐⭐⭐⭐⭐ | ⚠️ | ✅ | ⭐⭐⭐ |
| [draw.io / diagrams.net](https://github.com/jgraph/drawio-desktop) | Fluxos/diagramas | Win/Linux/macOS/Web; Electron/JS | Apache-2.0 | ✅ | ❌ | ⚠️ | ⭐⭐⭐⭐⭐ |
| [SVG-Edit](https://github.com/SVG-Edit/svgedit) | Editor vetorial | Navegador; JavaScript | MIT | ✅ | ✅ | ❌ | ⭐⭐⭐⭐ |
| Wireflow | User-flow | Web; JavaScript | MIT | ⭐⭐⭐⭐ | ❌ | ✅ (fluxo) | ⭐⭐⭐ |
| PlantUML Salt | Wireframe por texto | Multiplataforma; Java | Open source | ⭐⭐⭐⭐ | ❌ | ⚠️ | ⭐⭐⭐⭐ |
| WireMD | Wireframe por Markdown/IA | Win/Linux/macOS/Web; TypeScript | MIT | ⭐⭐⭐⭐⭐ | ✅ (parcial) | ⚠️ | ⭐⭐⭐⭐⭐ |
| Akira | UI/UX nativo Linux | Linux; Vala + GTK | GPL-3.0 | ✅ | ✅ | ⚠️ | ⭐⭐⭐ |

Legenda: ✅ suporta bem · ⚠️ suporte parcial/limitado · ❌ não suporta · ⭐ nível de aderência ao objetivo.

## 2. Notas por projeto

### Penpot — principal descoberta
Editor de UI/UX completo: componentes, variantes, design tokens, CSS Grid, Flex Layout, prototipação, colaboração em tempo real, sistema de plugins, API e inspeção de CSS/SVG/HTML. Pode ser hospedado em servidor próprio (self-host). Arquitetura: frontend em ClojureScript sobre React, backend em Clojure, persistência em PostgreSQL. Licença MPL-2.0. Projeto muito ativo (v2.17.0, jul/2026, já com renderer WASM/Skia no visualizador de protótipos). Referência arquitetural principal para o módulo de UI/UX.

### Excalidraw — núcleo para wireframes
MIT, canvas infinito, formas, textos, imagens, bibliotecas de formas, exporta SVG/PNG/JSON aberto, colaboração e PWA offline. O próprio projeto cita uso explícito para wireframes. Disponível como pacote integrável (`@excalidraw/excalidraw`), permitindo embutir o editor dentro de outra aplicação em vez de copiar o projeto inteiro. Stack: React/TypeScript. Melhor candidato como base tecnológica do modo Wireframe.

### Quant-UX — protótipo + teste de usabilidade
Cobre o que falta após o protótipo: protótipo → teste com usuário → gravação → métricas → questionário → análise UX. Recursos: protótipos ilimitados, testes de usuários, canvas de prototipação, colaboração em tempo real, analytics e questionários. Self-hosted via Docker; frontend web + backend Java + MongoDB. Licença GPL-3.0. Referência para um futuro modo de Teste de Usabilidade.

### Pencil Project — conceitos de wireframe desktop
Focado em diagramas e prototipação de GUI (Windows/macOS/Linux, Electron/JS, GPL-2.0). Conceitos úteis: bibliotecas de componentes, páginas de mockup, componentes drag-and-drop, exportação, protótipos clicáveis, coleções personalizadas de widgets. Ritmo de releases baixo (última: 3.1.1) — não indicado como núcleo, mas útil como fonte de conceitos de interface.

### draw.io / diagrams.net — motor de fluxos
Não concorre com Figma, mas é excelente para fluxo de telas → jornada → estados → arquitetura → navegação. Desktop em Electron, Apache-2.0, disponível para Windows, Windows ARM, macOS e Linux; série 31.x segue atualizada em 2026. Forte referência para o editor de User Flow do Lumivox.

### SVG-Edit — motor vetorial leve
Editor de canvas vetorial que roda inteiramente no navegador (JavaScript, MIT), pode ser hospedado localmente e é documentado para uso embutido em outras aplicações. Serve como motor leve para retângulos, textos, ícones, componentes e SVG dentro de um editor visual próprio.

### Wireflow — wireframe + user flow
Une wireframe e fluxo de telas em vez de telas isoladas, com foco em colaboração em tempo real. MIT, mas projeto pequeno — mais útil como referência funcional do que como núcleo tecnológico.

### PlantUML Salt — wireframe por texto (interessante para IA)
Módulo do PlantUML dedicado a "wireframe graphical interface / UI mockups": descreve a interface em texto e gera o wireframe automaticamente. Base conceitual interessante para gerar telas a partir de comandos de IA (ex.: "crie uma tela de login com logotipo, campo usuário, campo senha, botão entrar e recuperar senha").

### WireMD — a descoberta mais interessante para IA
Projeto voltado a wireframes descritos por texto/Markdown, com licença MIT. Consegue gerar HTML, JSON, React, Tailwind, wireframe estilo sketch, wireframe limpo, estilo Material, componentes editáveis e preview em tempo real. Formato baseado em texto versionável por Git, pensado para uso por agentes de IA — altíssimo interesse para um Lumivox com IA local gerando telas a partir de descrições em linguagem natural.

### Akira — UI/UX nativo para Linux
Editor de UI/UX nativo em Vala + GTK (GPL-3.0), fora do padrão Electron/Web. O próprio projeto avisa que **não está pronto para produção** — serve apenas como fonte de estudo, não como base.

## 3. Arquitetura combinada proposta

```
                    NOSSO DESIGNER UI/UX
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
    WIREFRAME            DESIGN UI           USER FLOW
        │                   │                   │
   Excalidraw            Penpot            draw.io /
   WireMD (conceitos)                       Wireflow
        │                   │                   │
        └───────────┬───────┴───────────────────┘
                     ▼
                PROTOTIPAÇÃO
                     │
                     ▼
                 Quant-UX
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
    TESTE UX                 ANALYTICS
        │                         │
        └────────────┬────────────┘
                      ▼
                RELATÓRIO UX
```

Camada adicional de IA local:

```
IA LOCAL
   │
"crie uma tela de cadastro"
   │
   ▼
 WireMD
   │
JSON / estrutura
   │
   ▼
CANVAS DE DESIGN
   │
┌──────────┴──────────┐
▼                      ▼
Wireframe        Alta fidelidade
```

## 4. Seleção final para referência/adaptação

1. **Penpot** — arquitetura de UI/UX profissional.
2. **Excalidraw** — canvas e wireframe.
3. **WireMD** — geração de UI por IA/texto.
4. **draw.io** — fluxos e jornadas.
5. **Quant-UX** — protótipo, teste e métricas.

Observação de licenciamento: Excalidraw, WireMD e draw.io usam licenças permissivas (MIT/Apache-2.0), o que as torna mais simples de integrar ou usar como base de código. Penpot (MPL-2.0) e Quant-UX (GPL-3.0) exigem separação arquitetural e análise de licença antes de reaproveitar código diretamente (copyleft em nível de arquivo ou de projeto, respectivamente).

## 5. Impacto na auditoria

| Item | Estado atual | Com este módulo |
|---|---|---|
| 4. Wireframes | ⚠️ Parcial / não formal | ✅ Completo: low-fi, fluxos e protótipos formais |
| 5. Design UI/UX | ❌ Básico/incompleto | ✅ Editor visual, componentes, tokens, responsividade e prototipação |

Diferencial possível em relação a simplesmente integrar o Penpot: IA local para geração automática de wireframes, foco em acessibilidade, suporte Linux/Windows, funcionamento offline e exportação para código.

## 6. O que esta pesquisa NÃO cobre

Estas ferramentas resolvem bem a concepção visual, mas não fecham o ciclo completo de desenvolvimento do aplicativo:

| Parte do aplicativo | Cobertura |
|---|---|
| Wireframes | ✅ Excelente |
| Fluxo de telas / jornada | ✅ Excelente |
| UI/UX | ✅ Excelente |
| Design system/componentes | ✅ Muito boa |
| Protótipos clicáveis | ✅ Excelente |
| Testes de usabilidade | ✅ Com Quant-UX |
| Geração inicial por IA/texto | ✅ WireMD / integrações |
| Exportação SVG/assets | ✅ |
| Acessibilidade visual no design | ⚠️ Parcial |
| Código frontend real | ⚠️ Parcial |
| Backend / regras de negócio | ❌ |
| Banco de dados | ❌ |
| Login/autenticação | ❌ |
| APIs | ❌ |
| Armazenamento local/arquivos | ❌ |
| IA local | ❌ (precisa integrar) |
| Testes automatizados do programa | ❌ |
| Instalador Windows/Linux | ❌ |
| Build Android | ❌ |
| Atualizador automático | ❌ |
| Segurança do aplicativo | ❌ |
| Empacotamento/release | ❌ |

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
└──────────────────────────────┘
  ↓
DESENVOLVIMENTO REAL      ← ainda precisa pesquisar
  ↓
BACKEND / BANCO / APIs    ← ainda precisa pesquisar
  ↓
TESTES                    ← ainda precisa pesquisar
  ↓
ACESSIBILIDADE            ← precisa camada própria
  ↓
BUILD / INSTALADOR        ← ainda precisa pesquisar
  ↓
ATUALIZAÇÃO / RELEASE     ← ainda precisa pesquisar
```

## 7. Próximos passos

Ampliar a pesquisa open source (internacional, qualquer linguagem) para as demais camadas de uma "fábrica de aplicativos" completa:

1. **Product/Requirements Engine** — requisitos, histórias, casos de uso e arquitetura.
2. **Wireframe & UX Engine** — Excalidraw + WireMD + conceitos do Quant-UX (coberto por este documento).
3. **UI Designer Engine** — arquitetura inspirada no Penpot (coberto por este documento).
4. **Code Builder Engine** — transformar telas/componentes em código real.
5. **Backend Builder** — APIs, banco de dados, autenticação e armazenamento.
6. **Accessibility Engine** — WCAG, teclado, leitor de tela, contraste, CAA, Braille etc.
7. **QA/Test Engine** — testes unitários, integração, GUI e acessibilidade.
8. **Build & Release Engine** — Windows, Linux, Android, instalador, atualização e assinatura.

```
FÁBRICA DE APLICATIVOS
        │
┌───────────────┼────────────────┐
▼               ▼                ▼
REQUISITOS   DESIGN/UX        CÓDIGO
        │               │                │
        └───────────────┼────────────────┘
                        ▼
                  APP FUNCIONAL
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
    TESTES        ACESSIBILIDADE     SEGURANÇA
        └───────────────┼────────────────┘
                        ▼
                 BUILD / RELEASE
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
    Windows           Linux           Android
```

O próximo levantamento deve cobrir, mundialmente e em qualquer linguagem, projetos open source de geração de código, backend, banco de dados, testes, acessibilidade, compilação e instaladores, para montar uma matriz completa do requisito até o aplicativo instalável.
