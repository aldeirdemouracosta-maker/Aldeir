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
    """Procura a pasta da voz sem diferenciar maiúsculas (versões antigas usam 'leticia-f123')."""
    for base in PASTAS_VOZES:
        try:
            for pasta in base.iterdir():
                if pasta.is_dir() and pasta.name.lower() == voz.lower():
                    return pasta
        except OSError:
            continue
    return None


def voz_no_speechd(listagem: str, busca: str = "leticia") -> str | None:
    """Acha o nome da voz na saída de 'spd-say -o rhvoice -L' (1ª coluna)."""
    for linha in listagem.splitlines():
        partes = linha.split()
        if partes and busca in partes[0].lower():
            return partes[0]
    return None


class RHVoiceEngine(TTSEngine):
    """
    Três caminhos, na ordem:
      1. RHVoice-test  (Linux, pacote 'rhvoice') — fala e gera arquivo de áudio
      2. speech-dispatcher com o módulo rhvoice — o mesmo caminho do Orca;
         fala ao vivo (não gera arquivo)
      3. SAPI5 (Windows) — fala e gera arquivo
    """

    name = "Letícia (RHVoice)"

    def __init__(self, voice: str = VOZ_PADRAO, rate_percent: int = 60):
        self.voice = voice
        self.rate_percent = rate_percent          # 0-100 (50 = normal)
        self.windows = platform.system() == "Windows"
        self._binario = None if self.windows else shutil.which("RHVoice-test")
        self._spd = None if self.windows else shutil.which("spd-say")
        self._voz_spd: str | None = None
        self._rota: str | None = None
        self._verificado = False

    # ---------------------------------------------------------------- disponibilidade

    @property
    def rota(self) -> str | None:
        """'rhvoice-test', 'speechd', 'sapi' ou None."""
        if not self._verificado:
            self._verificado = True
            if self.windows:
                self._rota = "sapi" if self._sapi("", listar=True) == 0 else None
            elif self._binario and _pasta_da_voz(self.voice):
                self._rota = "rhvoice-test"
            elif self._spd:
                try:
                    r = subprocess.run([self._spd, "-o", "rhvoice", "-L"], capture_output=True, timeout=10)
                    self._voz_spd = voz_no_speechd(r.stdout.decode("utf-8", "replace"))
                except (OSError, subprocess.TimeoutExpired):
                    self._voz_spd = None
                self._rota = "speechd" if self._voz_spd else None
        return self._rota

    def is_available(self) -> bool:
        return self.rota is not None

    @property
    def gera_arquivo(self) -> bool:
        """Pelo speech-dispatcher a Letícia só fala ao vivo; não grava arquivo de áudio."""
        return self.rota in ("rhvoice-test", "sapi")

    def descricao_rota(self) -> str:
        return {
            "rhvoice-test": "pelo RHVoice",
            "speechd": "pelo speech-dispatcher, como o Orca (só leitura ao vivo)",
            "sapi": "pelas vozes do Windows (SAPI5)",
        }.get(self.rota or "", "")

    def motivo_indisponivel(self) -> str:
        if self.windows:
            return "Instale a voz Letícia do RHVoice para Windows (SAPI5), em rhvoice.org."
        return ("Instale com: sudo apt install rhvoice rhvoice-brazilian-portuguese "
                "(ou, para o speech-dispatcher: speech-dispatcher-rhvoice)")

    # ---------------------------------------------------------------- síntese

    def comando_fala(self, texto: str) -> tuple[list[str], bytes | None]:
        """Comando que fala `texto` ao vivo e termina quando acabar; e o que mandar na entrada padrão."""
        if self.rota == "speechd":
            taxa = (self.rate_percent - 50) * 2  # speech-dispatcher: -100..100
            return [self._spd, "-o", "rhvoice", "-y", self._voz_spd, "-r", str(taxa), "-w", texto], None
        return [self._binario, "-p", self.voice, "-r", str(self.rate_percent)], texto.encode("utf-8")

    def cancelar(self) -> None:
        """Cala a fala em andamento (no speech-dispatcher, matar o spd-say não basta)."""
        if self.rota == "speechd":
            try:
                subprocess.run([self._spd, "-C"], capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        if not self.is_available():
            raise RuntimeError(f"Voz Letícia indisponível. {self.motivo_indisponivel()}")
        if not self.gera_arquivo:
            raise RuntimeError(
                "A Letícia está instalada só no speech-dispatcher, que fala ao vivo mas não grava "
                "arquivo. Use 'Ouvir com a Letícia agora' ou instale: sudo apt install rhvoice"
            )
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.windows:
            codigo = self._sapi(text, wav=output_path)
            if codigo != 0:
                raise RuntimeError(f"A síntese com a voz Letícia (SAPI5) falhou (código {codigo}).")
        else:
            args, entrada = self.comando_fala(text)
            subprocess.run(args + ["-o", str(output_path)], input=entrada, check=True, capture_output=True)
        return output_path

    def speak(self, text: str) -> None:
        if not self.is_available():
            raise RuntimeError(f"Voz Letícia indisponível. {self.motivo_indisponivel()}")
        if self.windows:
            self._sapi(text)
        else:
            args, entrada = self.comando_fala(text)
            subprocess.run(args, input=entrada, check=True)

    def iniciar_fala(self, texto: str) -> subprocess.Popen:
        """Começa a falar sem esperar terminar; o processo pode ser interrompido (feedback sonoro)."""
        if self.windows:
            powershell = shutil.which("powershell") or shutil.which("pwsh")
            script, env = self._preparar_sapi(texto)
            return subprocess.Popen(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_SEM_JANELA,
            )
        args, entrada = self.comando_fala(texto)
        proc = subprocess.Popen(args, stdin=subprocess.PIPE if entrada else subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if entrada:
            try:
                proc.stdin.write(entrada)
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
