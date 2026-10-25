# Módulos e laboratórios

## Manifesto (`module.json`) — contrato
```json
{
  "id": "lab.zip",
  "nome": "ZIP e compactados",
  "versao": "0.1.0",
  "local": "iso | externo",
  "tamanho_mb": 0,
  "dependencias": { "modulos": ["core"], "pacotes_debian": ["p7zip-full"], "binarios": ["7z"] },
  "permissoes": { "leitura": ["/mnt/evidencias"], "escrita": ["/workspace"], "rede": false,
                  "executa_amostras": false, "grava_firmware": false },
  "verificacao": { "fumaca": "tests/smoke.sh", "sha256_arquivos": "SHA256SUMS" },
  "testes": ["tests/unit", "tests/smoke.sh"],
  "estado": "planejado | instalavel | disponivel | quebrado"
}
```
**Disponibilidade** (mostrada na UI) é calculada: `disponivel` só se dependências presentes **e** SHA256SUMS confere **e** o teste de
fumaça passou nesta inicialização (ou foi aprovado e registrado para a mesma versão). Caso contrário `instalavel`/`quebrado`
com o motivo. `executa_amostras` e `grava_firmware` são `false` e **não podem ser alterados por manifesto** (o Guardian ignora).

## Laboratórios previstos (todos `planejado`; ferramentas citadas são candidatas **não testadas**)
| Id | Laboratório | Local | Candidatas | Observação |
|---|---|---|---|---|
| lab.apps | Aplicativos | externo | readelf/objdump, Ghidra (via módulo) | PE/ELF primeiro |
| lab.tvbox | TV Box | externo | binwalk, mtd-utils, dtc, simg2img | firmware **só leitura** |
| lab.iso | ISO e SO | iso/ext. | xorriso, 7z, isoinfo | monta em ro (loop) |
| lab.rom | ROMs | externo | identificação por cabeçalho/hash | consoles após PE/ELF |
| lab.video | Vídeos | externo | ffprobe/mediainfo | só metadados por padrão |
| lab.bios | BIOS e firmware | externo | binwalk, UEFITool-like | **nunca grava** |
| lab.drivers | Drivers e GPU | externo | lspci, vulkaninfo, glxinfo | inventário |
| lab.mobile | Mobile | externo | unzip/aapt-like para APK | sem executar |
| lab.rede | Redes | externo | tshark/tcpdump (pcap offline) | captura ao vivo exige autorização |
| lab.discos | Discos | externo | sleuthkit, smartctl, lsblk | **somente leitura**, bloqueio de escrita |
| lab.ia | Modelos de IA | externo | leitura de cabeçalho GGUF | hash e metadados |
| lab.formatos | Formatos binários | iso | file, xxd, strings, magic próprio | núcleo |
| lab.zip | ZIP/compactados | iso | 7z, unzip, tar | proteção contra zip-bomb/path traversal |
| lab.links | Links da internet | externo | curl | **download só com autorização**, em quarentena |
| lab.docs | Documentos | externo | pdfinfo, oletools-like | sem abrir macros |

Cada laboratório tem: manifesto, testes unitários, teste de fumaça com amostras inofensivas versionadas, e entrada no
relatório de disponibilidade. Ordem de implementação em `PLANO-DE-FASES.md`.
