# Ferramentas necessárias — App de engenharia reversa (ROM hacking)

Especificação mínima para implementação por outro agente (Codex). Ordem = ordem de implementação.
Princípio: um **núcleo único** (formato de dados + patches) e módulos finos por cima. Nada de UI antes do núcleo.

## 0. Núcleo compartilhado (pré-requisito de todos os módulos)

| Ferramenta | Função | Entrada → Saída |
|---|---|---|
| `RomFile` | Abrir ROM somente-leitura em memória, detectar plataforma (GBA/PS1/NDS) por header/tamanho/CRC32 | arquivo → `RomInfo{platform, crc32, size}` |
| `Schema` | Descrição declarativa (JSON/YAML) de estruturas: offset, tipo, tamanho, endianness, ponteiros | schema + ROM → registros tipados |
| `PointerMap` | Resolver/realocar ponteiros (GBA `0x08xxxxxx`, PS1 RAM `0x80xxxxxx`) | offset ↔ ponteiro |
| `ChangeSet` | Lista de edições (offset, bytes antigos, bytes novos). Única forma de alterar dados | edições → `ChangeSet` |
| `Undo/Redo` | Pilha sobre `ChangeSet` | — |

Regra: nenhum módulo escreve na ROM; todos produzem `ChangeSet`. A ROM original nunca é modificada.

## 1. Structured Hex Editor (implementar primeiro)
Ref.: BNE2, FEBuilderGBA.
- Visualização hex + painel de **estrutura** (campos nomeados via `Schema`).
- Busca: bytes, texto (tabela de caracteres `.tbl`), ponteiros que apontam para um offset.
- Seguir ponteiro (clique) e "quem referencia isto".
- Edição por campo → `ChangeSet`; diff visual contra ROM original.
- Importar/exportar `.tbl` e schemas.

## 2. Character Studio
Ref.: Shishi, celPix.
- Decodificadores: tiles 4bpp/8bpp (GBA/NDS), TIM + CLUT (PS1), paletas BGR555.
- Visualizador/editor de paleta, tile e sprite (OAM/composição de células).
- Exportar/importar PNG indexado; reimportar gera `ChangeSet` (valida tamanho/compressão).
- Compressões: LZ77 (GBA), RLE; interface `Codec{decode,encode}` extensível.

## 3. Skill & Magic Editor
Ref.: FFTPatcher, SkillSystem FE8.
- **Sem lógica própria**: tabelas editáveis geradas de `Schema` (habilidades, magias, custos, alcance, flags).
- Catálogo em JSON (`id`, nome, descrição, offset da struct) por jogo.
- Validação: ranges, flags conhecidas, referências cruzadas (item→skill).
- Exportar catálogo para CSV/JSON.

## 4. Battle Animation Studio
Ref.: ExMateria, DSVEdit.
- Linha do tempo de frames (reusa Character Studio) + comandos de animação (script de opcodes via `Schema`).
- Pré-visualização de quadros e sincronização com áudio.
- Áudio: extrair/tocar amostras (PCM/ADPCM/VAG), mapear SFX ↔ comando de animação.
- Entregar por último; depende de 1, 2 e do decoder de áudio.

## 5. Patch Manager (modo simulação primeiro)
Ref.: FEBuilderGBA.
- Formatos: IPS, UPS, BPS (aplicar e **gerar** a partir de `ChangeSet`).
- **Dry-run obrigatório**: mostra offsets afetados, conflitos entre patches e checksum antes/depois, sem escrever.
- Pilha de patches ordenada + verificação de CRC da ROM base.
- Saída: nova ROM em arquivo separado; ROM original intocada.

## Requisitos transversais
- Distribuir **apenas patches/schemas**, nunca ROMs ou assets extraídos (direitos autorais).
- Testes: round-trip (decode→encode == original) para cada Codec; dry-run não altera bytes.
- Local/offline; sem telemetria.

## Critério de pronto por etapa
1. Núcleo + Hex Editor: abre ROM, edita campo por schema, desfaz, exporta IPS.
2. Character Studio: ida e volta PNG↔tile sem diferença de bytes.
3. Skill/Magic: edita 1 tabela real e passa na validação.
4. Battle Animation: reproduz 1 animação + 1 SFX.
5. Patch Manager: aplica/gera BPS com dry-run.
