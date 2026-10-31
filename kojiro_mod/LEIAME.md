# Kojiro jogável — assets (Captain Commando, CPS-1 / MAME)

Sprites originais rips de **T0misaurus** — dê crédito na mod.

## Pastas
- `frames/kojiro_original/` — quadros originais do Kojiro (socos, chutes, dano, queda, "grabbed", giro de pulo). **Use estes para os ataques básicos.**
- `frames/kojiro_movimento_ginzu/` — quadros de movimentação do Ginzu recoloridos com a paleta do Kojiro, **sem katana**: `idle`, `walk`, `run`, `jump`, `jump_roll`, `jump_attack`, `flip_kick`, `grab_punch`.
- `portrait/kojiro_portrait_96x96.png` — retrato de seleção (do retrato do Ginzu: katana removida, paleta do Kojiro, fundo azul para contrastar). `kojiro_portrait_x4.png` é só preview.
- `portrait/kojiro_nameplate.png` — plaquinha com ícone + "KOJIRO".
- `kojiro_paleta_16cores.png` / `kojiro_paleta.json` — paleta de 15 cores + índice 0 transparente (cabe em 1 palette de sprite CPS-1, 16 cores).
- `preview_*.png` — folhas de conferência.

## Reproduzir
`python3 build_frames.py` e `python3 build_portrait.py` (Pillow + numpy). Os `*_boxes.json` guardam o recorte de cada quadro nos sheets.

## Observações
- Todo quadro usa só cores da paleta de 15 cores do Kojiro.
- Os quadros do Ginzu não têm o rabo de cavalo/cachecol laranja do Kojiro; os do Kojiro original têm.
- Não há quadros de dash/combo com katana (você quer só socos e chutes).
