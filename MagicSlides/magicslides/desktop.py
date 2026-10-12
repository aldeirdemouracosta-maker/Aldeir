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
    """Funções chamadas pelo JavaScript dentro da janela nativa.

    Atenção: o pywebview percorre todos os atributos PÚBLICOS deste objeto
    para expô-los ao JavaScript. Guardar a janela num atributo público faz
    ele varrer o objeto Window (posição, DOM...), o que trava a interface
    no Windows. Por isso a janela fica em `_window` (privado).
    """

    def __init__(self):
        self._window = None

    def attach(self, window) -> None:
        self._window = window

    def save_file(self, filename: str, b64: str) -> dict:
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or getattr(webview, "SAVE_DIALOG", 30)
        result = self._window.create_file_dialog(dialog, save_filename=Path(str(filename)).name)
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


def _selftest(window, result: dict) -> None:
    """Confere que a janela carregou, que a ponte JS↔Python responde e que
    o editor iniciou. Qualquer travamento vira falha por tempo esgotado."""
    import time
    try:
        if not window.events.loaded.wait(60):
            print("SELFTEST FALHOU: a página não terminou de carregar (janela travada?)")
            return
        bridge = window.evaluate_js("typeof (window.pywebview && window.pywebview.api && window.pywebview.api.save_file)")
        slides = ""
        for _ in range(60):
            slides = window.evaluate_js("document.getElementById('slideCount').textContent") or ""
            if slides:
                break
            time.sleep(0.5)
        print(f"SELFTEST ponte={bridge} slides={slides!r}")
        if bridge == "function" and slides:
            result["code"] = 0
            print("SELFTEST OK")
        else:
            print("SELFTEST FALHOU")
    except Exception as exc:
        print(f"SELFTEST FALHOU: {exc}")
    finally:
        window.destroy()


def main(argv: list[str] | None = None) -> None:
    _ensure_log_streams()
    ap = argparse.ArgumentParser(prog=APP_NAME, description=f"{APP_NAME} {__version__}")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--browser", action="store_true", help="abrir no navegador em vez da janela nativa")
    ap.add_argument("--no-window", action="store_true", help="só iniciar o servidor (sem abrir nada)")
    ap.add_argument("--selftest", action="store_true", help="abre a janela, confere se a interface carregou e sai (usado no CI)")
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
                    api.attach(window)
                    from .config import config_dir
                    result = {"code": 1}
                    func = (lambda: _selftest(window, result)) if args.selftest else None
                    # private_mode=False mantém o salvamento automático entre sessões.
                    webview.start(func, private_mode=False, storage_path=str(config_dir() / "webview"))
                    if args.selftest:
                        sys.exit(result["code"])
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
