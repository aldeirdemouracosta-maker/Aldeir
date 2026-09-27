# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: gera dist/MagicSlides/MagicSlides.exe (pasta "onedir").
# Uso (na pasta MagicSlides):  pyinstaller packaging/MagicSlides.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_WIN = sys.platform.startswith("win")

datas = [(os.path.join(ROOT, "magicslides", "static"), "magicslides/static")]
datas += collect_data_files("pptx")
hiddenimports = collect_submodules("magicslides")
try:
    import webview  # noqa: F401
    hiddenimports += ["webview"]
except ImportError:
    pass

a = Analysis(
    [os.path.join(ROOT, "MagicSlides.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "numpy", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MagicSlides",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    console=not IS_WIN,  # no Windows abre só a janela, sem terminal
    version=os.path.join(SPECPATH, "version_info.txt") if IS_WIN else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MagicSlides")
