# LumePDF

Caixa de ferramentas de PDF para Windows (também roda no Linux e no macOS), no estilo do iLovePDF, mas **100% local**: nenhum arquivo sai do seu computador.

## Ferramentas
Juntar · Dividir · Extrair páginas · Remover páginas · Reordenar · Girar · Comprimir (leve/média/forte) · Imagem → PDF · PDF → imagem (JPG/PNG) · PDF → texto · Marca d'água · Numerar páginas · Proteger com senha · Desbloquear

## Rodar
**Windows:** `instalar-windows.bat` (uma vez) e depois `executar-windows.bat`.
**Linux/macOS:** `./run-linux-macos.sh` (abre no navegador).

## Testes
```bash
pip install -r requirements.txt
PYTHONPATH=. python -m unittest discover -s tests
```

## Estrutura
- `lumepdf/core.py` — operações de PDF (pypdf, pypdfium2, Pillow, reportlab)
- `lumepdf/server.py` — servidor HTTP local (upload, ferramentas, download)
- `lumepdf/desktop.py` — janela nativa (pywebview) ou navegador
- `lumepdf/static/index.html` — interface
