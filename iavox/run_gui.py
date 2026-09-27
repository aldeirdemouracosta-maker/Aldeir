#!/usr/bin/env python3
"""Ponto de entrada da interface gráfica do IAVOX.

    python run_gui.py              abre o IAVOX
    python run_gui.py --verificar  monta a janela, confere as peças e sai (usado no build do Windows)
"""
import os
import platform
import sys

# Linux: sempre em modo UTF-8. Se o idioma do sistema (LANG/LC_ALL) estiver mal
# configurado, o Python cai para ASCII e qualquer texto com acento quebra
# ("'ascii' codec can't decode byte 0xc3"). Reinicia com -X utf8 nesse caso.
# (No Windows e no IAVOX.exe isso não é necessário nem possível com execv.)
if (not sys.flags.utf8_mode and os.environ.get("IAVOX_UTF8") != "1"
        and platform.system() != "Windows" and not getattr(sys, "frozen", False)):
    os.environ["IAVOX_UTF8"] = "1"
    os.execv(sys.executable, [sys.executable, "-X", "utf8", *sys.argv])


def verificar() -> int:
    """Abre a janela sem mostrar, confere módulos e recursos, e sai com 0 se estiver tudo certo."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    from gui.contexto import Config
    from gui.janela import JanelaIAVOX
    from iavox_pdf_audio.suite.ambiente import checar_tudo
    from iavox_pdf_audio.tts.selector import get_engine

    app = QApplication(sys.argv)
    janela = JanelaIAVOX(Config(feedback_sonoro=False))
    paginas = sorted(janela.paginas)
    assert paginas == sorted(["inicio", "leitor", "fala", "olha", "estuda", "atividade", "caderno", "ajuda"]), paginas
    from gui.componentes import ASSETS
    assert (ASSETS / "robo.png").exists(), "imagem do robô não empacotada"
    print("IAVOX OK — telas:", ", ".join(paginas))
    print("Voz automática:", get_engine("automatico").name, "| feedback:", janela.ctx.falador.voz)
    for st in checar_tudo():
        print(" -", st.fala)
    janela.close()
    app.quit()
    return 0


if __name__ == "__main__":
    if "--verificar" in sys.argv:
        # O IAVOX.exe (janela, sem console) não tem saída padrão: grava em verificar_exe.txt
        if sys.stdout is None:
            sys.stdout = sys.stderr = open("verificar_exe.txt", "w", encoding="utf-8")
        try:
            codigo = verificar()
        except BaseException:  # noqa: BLE001
            import traceback
            traceback.print_exc(file=sys.stdout)
            codigo = 1
        sys.stdout.flush()
        raise SystemExit(codigo)
    from gui.janela import main
    raise SystemExit(main())
