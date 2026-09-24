"""Roda ``minivideo-ui`` num pseudo-terminal real e renderiza a tela com pyte."""

import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time

import pyte


class Tui:
    def __init__(self, workspace, cols=100, rows=30, env=None):
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.environ.update({"TERM": "xterm", "LANG": "C.UTF-8", "ESCDELAY": "25",
                               "LINES": str(rows), "COLUMNS": str(cols)}, **(env or {}))
            os.execvp(sys.executable, [sys.executable, "-m", "minivideo_ui", "--workspace", workspace])
        self.pid, self.fd = pid, fd
        self.pump(1.5)

    def pump(self, seconds=0.6, quiet=0.3):
        """Lê a saída por pelo menos ``seconds`` e até ficar ``quiet`` s sem dados."""
        end = time.time() + seconds
        last = time.time()
        while time.time() < end or time.time() - last < quiet:
            if time.time() > end + 10:
                return
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                last = time.time()
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    return
                if not data:
                    return
                self.stream.feed(data)

    def send(self, keys, wait=0.6):
        os.write(self.fd, keys.encode() if isinstance(keys, str) else keys)
        self.pump(wait)

    def wait_for(self, needle, timeout=15.0):
        end = time.time() + timeout
        while needle not in self.text() and time.time() < end:
            self.pump(0.2)
        return needle in self.text()

    def text(self):
        return "\n".join(self.screen.display)

    def close(self):
        try:
            self.send("q", 0.5)
            os.waitpid(self.pid, 0)
        except (OSError, ChildProcessError):
            pass


DOWN, UP, LEFT, RIGHT = "\x1bOB", "\x1bOA", "\x1bOD", "\x1bOC"  # modo aplicação (keypad)
TAB, ENTER, ESC, F1 = "\t", "\r", "\x1b", "\x1bOP"
