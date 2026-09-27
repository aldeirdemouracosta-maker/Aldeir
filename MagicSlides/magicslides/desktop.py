"""Inicia o MagicSlides como aplicativo de desktop.

Com `pywebview` instalado (padrão no instalador Windows), abre uma janela
nativa (Edge WebView2 no Windows). Sem ele, abre no navegador padrão.
"""
from __future__ import annotations

import argparse
import base64
import sys
import threading
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__
from .server import make_server


class DesktopApi:
    """Funções chamadas pelo JavaScript dentro da janela nativa."""

    def __init__(self):
        self.window = None

    def save_file(self, filename: str, b64: str) -> dict:
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or getattr(webview, "SAVE_DIALOG", 30)
        result = self.window.create_file_dialog(dialog, save_filename=Path(str(filename)).name)
        if not result:
            return {"ok": False, "cancelled": True}
        target = result if isinstance(result, str) else result[0]
        Path(target).write_bytes(base64.b64decode(b64))
        return {"ok": True, "path": str(target)}


def _ensure_log_streams() -> None:
    """No .exe sem console, stdout/stderr são None: grava num arquivo de log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from .config import config_dir
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        log = open(config_dir() / "magicslides.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        import io
        log = io.StringIO()
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main(argv: list[str] | None = None) -> None:
    _ensure_log_streams()
    ap = argparse.ArgumentParser(prog=APP_NAME, description=f"{APP_NAME} {__version__}")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--browser", action="store_true", help="abrir no navegador em vez da janela nativa")
    ap.add_argument("--no-window", action="store_true", help="só iniciar o servidor (sem abrir nada)")
    args = ap.parse_args(argv)

    httpd = make_server("127.0.0.1", args.port)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"{APP_NAME} {__version__} em {url}  (CTRL+C para encerrar)")

    try:
        if args.no_window:
            threading.Event().wait()
        if not args.browser:
            try:
                import webview
            except ImportError:
                webview = None
            if webview is not None:
                try:
                    api = DesktopApi()
                    window = webview.create_window(APP_NAME, url, js_api=api, width=1440, height=900,
                                                   min_size=(1024, 640), text_select=True)
                    api.window = window
                    from .config import config_dir
                    # private_mode=False mantém o salvamento automático entre sessões.
                    webview.start(private_mode=False, storage_path=str(config_dir() / "webview"))
                    return
                except Exception as exc:  # ex.: Edge WebView2 ausente
                    print(f"Janela nativa indisponível ({exc}); abrindo no navegador.")
            else:
                print("pywebview não instalado: abrindo no navegador.")
        webbrowser.open(url)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main(sys.argv[1:])
