# REA Core em Go (`core/`)

Binário único `rea`, **somente biblioteca padrão** (sem dependências; compila offline), estático (`CGO_ENABLED=0`), ~6 MB.
Escolhido por: um executável simples para a ISO, baixo consumo de RAM, build cruzado trivial (Linux e Windows) e fácil
auditoria. Verificado nesta sessão: `go vet` limpo, `go test ./...` aprovado, build linux/amd64 e windows/amd64.

## Comandos (todos testados em execução real nesta sessão, Linux)
| Comando | O que faz de fato |
|---|---|
| `rea modulos [-json]` | estado **real** de cada um dos 15 laboratórios: `disponivel` só se há código + dependências + teste de fumaça aprovado agora |
| `rea ferramentas [-v] [-json]` | procura no PATH as ferramentas do catálogo; separa "presente, com adaptador" de "presente, sem adaptador ainda" |
| `rea hash`, `rea detectar` | SHA-256 e formato por assinatura (PE, ELF, ZIP, GZIP, 7z, XZ, BZ2, RAR, PDF, GGUF, SquashFS, ISO9660, TAR, Mach-O, OLE2, PNG) |
| `rea zip` | lista ZIP com alertas de path traversal, symlink, criptografia, razão de compressão e total (anti zip-bomb); **não extrai** |
| `rea analisar [--saida DIR] [--autorizado-por] [--origem] arquivo` | pipeline estático (`file`, `strings`, `readelf`, `objdump`, `pdfinfo` conforme o formato e a disponibilidade), SHA-256 antes/depois, relatório JSON + Markdown com proveniência |
| `rea ia [-remoto URL -autorizo-remoto]` | detecta Ollama (11434), llama-server (8080), LM Studio (1234) e aceleradores; remoto só com autorização |

## Ferramentas com adaptador (executadas só em modo leitura, 20 s e 256 KiB no máximo, via Guardian)
`file`, `strings`, `readelf`, `objdump`, `unzip` (sob demanda), `pdfinfo`, `ffprobe` (sob demanda). Estado depende do host:
na sessão de desenvolvimento todas estavam presentes; na ISO, só as incluídas nos pacotes.
**Detectadas, sem adaptador:** binwalk, 7z, xorriso, mediainfo, lsblk, smartctl, nmap, tshark, tcpdump, curl, aapt, dtc,
simg2img, mmls, lspci, vulkaninfo, glxinfo, ollama, llama-server, qemu-img, qemu-system-x86_64.

## Estado dos módulos (medido)
`lab.formatos` e `lab.zip`: **disponíveis** (embutidos em Go, teste de fumaça aprovado). Os outros 13: **planejados**
(a presença de ferramentas é mostrada, mas o módulo só vira disponível quando o adaptador for implementado e testado).

## Guardian (testado)
Bloqueia execução de `dd`, `mkfs*`, `fdisk`, `parted`, `wipefs`, `flashrom`, `fwupd*`, `rm`, `mv`, `cp`...; leitura só de arquivos
regulares (nega dispositivos, pipes e diretórios); escrita só na área de trabalho; rede só em loopback, remoto com autorização;
manifestos com `executa_amostras` ou `grava_firmware` verdadeiros são rejeitados. Saída hostil de ferramentas não quebra o
relatório Markdown (cerca de crases dinâmica).

## Limitações reais
- Ainda não há serviços residentes (AutoLab, Projects, Chat, Full), só o Core em modo CLI.
- Adaptadores de IA: detecção e `Complete` testados contra servidores simulados; **não** foram testados contra Ollama,
  llama.cpp ou LM Studio reais (ausentes na sessão). CUDA/Vulkan: só presença do utilitário, não suporte efetivo.
- Não testado em Windows nem na ISO. Ferramentas externas analisam entrada não confiável (parsers podem ter falhas); a
  mitigação (limites, usuário sem privilégio, sem rede) depende da ISO e ainda não existe.
- Relatórios não são assinados.

## Uso
```
cd core && go test ./... && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o rea ./cmd/rea
./rea modulos ; ./rea analisar --saida rea-saida --autorizado-por "Nome" arquivo
```
