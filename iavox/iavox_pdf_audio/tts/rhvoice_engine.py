"""
Motor de TTS com a voz Letícia-F123 (RHVoice) — a mesma voz brasileira usada
pelo leitor de tela Orca no Linux e pelo NVDA/DOSVOX no Windows. 100% offline.

Linux (Ubuntu/Debian):
    sudo apt install rhvoice rhvoice-brazilian-portuguese
    -> usa o programa RHVoice-test.

Windows:
    instale a voz Letícia do RHVoice para SAPI5 (https://rhvoice.org).
    -> usa a síntese de voz do próprio Windows (System.Speech), sem pacotes extras.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import TTSEngine

VOZ_PADRAO = "Leticia-F123"
PASTAS_VOZES = [
    Path("/usr/share/RHVoice/voices"),
    Path("/usr/local/share/RHVoice/voices"),
    Path.home() / ".local/share/RHVoice/voices",
]
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# PowerShell: fala (ou grava em WAV) com a primeira voz SAPI5 cujo nome contém "Leticia".
_PS_SAPI = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name } | Where-Object { $_ -like '*{busca}*' } | Select-Object -First 1
if (-not $v) { exit 3 }
if ($env:IAVOX_LISTAR) { Write-Output $v; exit 0 }
$s.SelectVoice($v)
$s.Rate = {taxa}
if ($env:IAVOX_WAV) { $s.SetOutputToWaveFile($env:IAVOX_WAV) } else { $s.SetOutputToDefaultAudioDevice() }
$s.Speak((Get-Content -LiteralPath $env:IAVOX_TXT -Encoding UTF8 -Raw))
"""


def _pasta_da_voz(voz: str) -> Path | None:
    for base in PASTAS_VOZES:
        if (base / voz).is_dir():
            return base / voz
    return None


class RHVoiceEngine(TTSEngine):
    name = "Letícia (RHVoice)"

    def __init__(self, voice: str = VOZ_PADRAO, rate_percent: int = 55):
        self.voice = voice
        self.rate_percent = rate_percent          # 0-100 (50 = normal)
        self.windows = platform.system() == "Windows"
        self._binario = None if self.windows else shutil.which("RHVoice-test")
        self._disponivel: bool | None = None

    # ---------------------------------------------------------------- disponibilidade

    def is_available(self) -> bool:
        if self._disponivel is None:
            if self.windows:
                self._disponivel = self._sapi("", listar=True) == 0
            else:
                self._disponivel = bool(self._binario and _pasta_da_voz(self.voice))
        return self._disponivel

    def motivo_indisponivel(self) -> str:
        if self.windows:
            return "Instale a voz Letícia do RHVoice para Windows (SAPI5), em rhvoice.org."
        if not self._binario:
            return "Instale com: sudo apt install rhvoice rhvoice-brazilian-portuguese"
        return f"A voz {self.voice} não foi encontrada. Instale: sudo apt install rhvoice-brazilian-portuguese"

    # ---------------------------------------------------------------- síntese

    def comando_fala(self) -> list[str]:
        """Comando que fala o texto recebido pela entrada padrão (usado pelo feedback sonoro)."""
        return [self._binario, "-p", self.voice, "-r", str(self.rate_percent)]

    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        if not self.is_available():
            raise RuntimeError(f"Voz Letícia indisponível. {self.motivo_indisponivel()}")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.windows:
            codigo = self._sapi(text, wav=output_path)
            if codigo != 0:
                raise RuntimeError(f"A síntese com a voz Letícia (SAPI5) falhou (código {codigo}).")
        else:
            subprocess.run(
                self.comando_fala() + ["-o", str(output_path)],
                input=text.encode("utf-8"), check=True, capture_output=True,
            )
        return output_path

    def speak(self, text: str) -> None:
        if not self.is_available():
            raise RuntimeError(f"Voz Letícia indisponível. {self.motivo_indisponivel()}")
        if self.windows:
            self._sapi(text)
        else:
            subprocess.run(self.comando_fala(), input=text.encode("utf-8"), check=True)

    def iniciar_fala(self, texto: str) -> subprocess.Popen:
        """Começa a falar sem esperar terminar; o processo pode ser interrompido (feedback sonoro)."""
        if self.windows:
            powershell = shutil.which("powershell") or shutil.which("pwsh")
            script, env = self._preparar_sapi(texto)
            return subprocess.Popen(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_SEM_JANELA,
            )
        proc = subprocess.Popen(self.comando_fala(), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.stdin.write(texto.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        return proc

    # ---------------------------------------------------------------- Windows

    def _preparar_sapi(self, texto: str, wav: Path | None = None, listar: bool = False):
        taxa = round((self.rate_percent - 50) / 5)  # SAPI: -10..10
        script = _PS_SAPI.replace("{busca}", self.voice.split("-")[0]).replace("{taxa}", str(taxa))
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(texto)
        env = dict(os.environ, IAVOX_TXT=f.name)
        if wav:
            env["IAVOX_WAV"] = str(wav)
        if listar:
            env["IAVOX_LISTAR"] = "1"
        return script, env

    def _sapi(self, texto: str, wav: Path | None = None, listar: bool = False) -> int:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return 127
        script, env = self._preparar_sapi(texto, wav, listar)
        txt = env["IAVOX_TXT"]
        try:
            r = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                env=env, capture_output=True, creationflags=_SEM_JANELA, timeout=None if not listar else 30,
            )
            return r.returncode
        except (OSError, subprocess.TimeoutExpired):
            return 1
        finally:
            Path(txt).unlink(missing_ok=True)
