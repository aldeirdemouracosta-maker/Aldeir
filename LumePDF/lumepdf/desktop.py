"""Inicia o LumePDF: janela nativa (pywebview) se disponível, senão o navegador padrão."""
from __future__ import annotations

import argparse
import threading
import webbrowser

from . import APP_NAME, __version__
from .server import make_server


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog=APP_NAME)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--browser", action="store_true", help="abrir no navegador em vez da janela nativa")
    args = ap.parse_args(argv)

    srv = make_server(port=args.port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        if args.browser:
            raise ImportError
        import webview
        webview.create_window(f"{APP_NAME} {__version__}", url, width=1180, height=800, min_size=(820, 600))
        webview.start()
    except ImportError:
        print(f"{APP_NAME} em {url} (Ctrl+C para sair)")
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    finally:
        srv.shutdown()
        srv.workspace.cleanup()
