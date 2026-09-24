"""Pastas de trabalho do IA-Linux MiniVideo.

No ISO a raiz é ``/data/minivideo`` (partição rotulada MV_DADOS). Sem essa
partição, ou fora do ISO, usa ``$MINIVIDEO_HOME`` ou ``~/MiniVideo``.
"""

from __future__ import annotations

import os
from typing import List, Optional

FOLDERS = ("Projetos", "Midia", "Modelos", "Ferramentas", "Saidas", "Jobs", "Logs")
SYSTEM_MODELS = "/usr/share/minivideo/modelos"


def default_root() -> str:
    env = os.environ.get("MINIVIDEO_HOME")
    if env:
        return env
    if os.path.ismount("/data") and os.access("/data", os.W_OK):
        return "/data/minivideo"
    return os.path.join(os.path.expanduser("~"), "MiniVideo")


def is_persistent(root: str) -> bool:
    """False quando a pasta está em RAM (tmpfs/rootfs do ISO): some ao desligar."""
    path = os.path.realpath(root)
    best, fstype = "", None
    try:
        with open("/proc/mounts") as fh:
            for line in fh:
                parts = line.split()
                mnt = parts[1]
                if (path == mnt or path.startswith(mnt.rstrip("/") + "/")) and len(mnt) >= len(best):
                    best, fstype = mnt, parts[2]
    except OSError:
        return True
    return fstype not in ("tmpfs", "rootfs", "ramfs")


class Workspace:
    def __init__(self, root: Optional[str] = None):
        self.root = os.path.abspath(root or default_root())
        for f in FOLDERS:
            os.makedirs(os.path.join(self.root, f), exist_ok=True)

    def path(self, folder: str) -> str:
        return os.path.join(self.root, folder)

    @property
    def jobs(self) -> str:
        return self.path("Jobs")

    @property
    def logs(self) -> str:
        return self.path("Logs")

    @property
    def models_dirs(self) -> List[str]:
        return [self.path("Modelos"), SYSTEM_MODELS]

    @property
    def persistent(self) -> bool:
        return is_persistent(self.root)
