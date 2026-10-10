import os
import shutil
import stat
import uuid
from pathlib import Path


class WorkspaceTemp:
    def __init__(self):
        self.path = Path(__file__).resolve().parent / ("fixture-" + uuid.uuid4().hex)
        self.path.mkdir()
        self.name = str(self.path)
    def cleanup(self):
        def remove_readonly(func, path, exc):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(self.path, onexc=remove_readonly)
