#!/usr/bin/env python3
"""Painel REA - interface do REA Linux (PySide6).

Status do laboratorio, atalhos para Ghidra/Codex, modo Ghidra (janela ou headless),
download de modelos, refinador de pseudocodigo (LLM4Decompile) e diagnostico do contexto.
Usa somente a biblioteca padrao + PySide6.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ---------------- configuracao ----------------
OLLAMA = os.environ.get("REA_OLLAMA", "http://127.0.0.1:11434")
PORTA_GHIDRA = int(os.environ.get("REA_PORTA_GHIDRA", "8080"))
MODELO_AGENTE = "qwen3-8b-gpu:latest"
MODELO_DECOMP = "llm4decompile-cpu:latest"
GHIDRA_DIR = os.environ.get("GHIDRA_INSTALL_DIR", "/opt/ghidra/atual")
EXT_JAR = os.environ.get("REA_EXTENSAO_GHIDRAMCP", "/opt/ghidra-mcp/ext/GhidraMCP/lib/GhidraMCP.jar")
GHIDRA_MCP = shutil.which("ghidra-mcp") or "/usr/local/bin/ghidra-mcp"
REA_BIN = shutil.which("rea") or "/usr/local/bin/rea"
CODEX_CFG = Path.home() / ".codex" / "config.toml"
PROJETOS = Path(os.environ.get("REA_PROJETOS", str(Path.home() / "rea-projetos")))
LOG_OLLAMA = Path("/var/log/ollama/ollama.log")

FERRAMENTAS_GHIDRA = [
    "get_program_info", "list_functions", "search_functions_by_name", "decompile_function",
    "decompile_function_by_address", "get_xrefs_to", "list_strings", "list_imports",
    "rename_function", "set_decompiler_comment",
]
MARCA_INI = "# >>> rea-painel"
MARCA_FIM = "# <<< rea-painel"


# ---------------- funcoes de apoio (testaveis sem interface) ----------------
def ollama_get(rota: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(OLLAMA + rota, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def ollama_post(rota: str, dados: dict, timeout: float = 900.0):
    req = urllib.request.Request(
        OLLAMA + rota, data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def porta_aberta(porta: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, porta), timeout=0.3):
            return True
    except OSError:
        return False


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def toml_lista(itens) -> str:
    return "[" + ", ".join(toml_str(i) for i in itens) + "]"


def bloco_mcp(modo: str, binario: str | None = None) -> str:
    """Gera o bloco de servidores MCP do Codex. modo = 'janela' ou 'headless'."""
    if modo == "headless":
        if not binario:
            raise ValueError("modo headless exige um binario")
        projeto = PROJETOS / "ghidra"
        args = ["--headless", "--binary", binario, "--project", str(projeto),
                "--ghidra-install-dir", GHIDRA_DIR, "--extension-jar", EXT_JAR]
        timeout_inicio = 600  # importacao + analise inicial do binario
    else:
        args = ["--ghidra-server", f"http://127.0.0.1:{PORTA_GHIDRA}/"]
        timeout_inicio = 60
    return "\n".join([
        MARCA_INI,
        f"# modo: {modo}" + (f" | binario: {binario}" if binario else ""),
        "[mcp_servers.ghidra]",
        f"command = {toml_str(GHIDRA_MCP)}",
        f"args = {toml_lista(args)}",
        f"enabled_tools = {toml_lista(FERRAMENTAS_GHIDRA)}",
        f"startup_timeout_sec = {timeout_inicio}",
        "tool_timeout_sec = 180",
        "",
        "[mcp_servers.rea]",
        f"command = {toml_str(REA_BIN)}",
        'args = ["mcp"]',
        'enabled_tools = ["binary_session"]',
        "startup_timeout_sec = 30",
        "tool_timeout_sec = 120",
        MARCA_FIM,
    ])


def aplicar_bloco(texto: str, bloco: str) -> str:
    """Troca o bloco entre as marcas; se nao existir, acrescenta no fim."""
    padrao = re.compile(re.escape(MARCA_INI) + r".*?" + re.escape(MARCA_FIM), re.DOTALL)
    if padrao.search(texto):
        return padrao.sub(lambda _m: bloco, texto, count=1)
    if f'model = "{MODELO_AGENTE}"' not in texto and not re.search(r"^model\s*=", texto, re.MULTILINE):
        texto = f'model = "{MODELO_AGENTE}"\n' + texto
    return texto.rstrip() + "\n\n" + bloco + "\n"


def modo_atual(texto: str) -> str:
    m = re.search(r"# modo: (\w+)(?: \| binario: (.+))?", texto)
    if not m:
        return "desconhecido"
    return m.group(1) + (f" ({Path(m.group(2)).name})" if m.group(2) else "")


def prompt_decomp(pseudo: str) -> str:
    return "# This is the assembly code:\n" + pseudo.strip() + "\n# What is the source code?\n"


def cortes_no_log(caminho: Path, ultimos: int = 3):
    if not caminho.exists():
        return None
    achados = []
    with caminho.open("r", encoding="utf-8", errors="replace") as f:
        for linha in f:
            if "truncating input prompt" in linha:
                hora = re.search(r"time=(\S+)", linha)
                lim = re.search(r"limit=(\d+)", linha)
                pr = re.search(r"prompt=(\d+)", linha)
                achados.append((hora.group(1) if hora else "?",
                                pr.group(1) if pr else "?", lim.group(1) if lim else "?"))
    return achados[-ultimos:]


def abrir_terminal(comando: list[str]) -> None:
    subprocess.Popen(["xterm", "-fa", "Monospace", "-fs", "11", "-e", *comando])


# ---------------- trabalho em segundo plano ----------------
class Refinador(QObject):
    pronto = Signal(str)
    erro = Signal(str)

    def __init__(self, pseudo: str):
        super().__init__()
        self.pseudo = pseudo

    def executar(self):
        try:
            r = ollama_post("/api/generate", {
                "model": MODELO_DECOMP, "prompt": prompt_decomp(self.pseudo), "raw": True,
                "stream": False, "keep_alive": "30m",
                "options": {"temperature": 0, "num_predict": 1024},
            })
            self.pronto.emit(r.get("response", ""))
        except Exception as e:  # noqa: BLE001 - mostrar qualquer falha ao usuario
            self.erro.emit(str(e))


# ---------------- janela ----------------
class Painel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Painel REA")
        self.resize(1000, 760)
        self._thread = None

        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)

        # status
        grp_status = QGroupBox("Status (atualiza a cada 5 s)")
        g = QGridLayout(grp_status)
        self.lbl = {}
        for i, chave in enumerate(["ollama", "modelos", "carregados", "ghidra", "modo", "disco"]):
            rotulo = QLabel()
            rotulo.setWordWrap(True)
            self.lbl[chave] = rotulo
            g.addWidget(rotulo, i // 2, i % 2)
        raiz.addWidget(grp_status)

        # acoes
        grp_acoes = QGroupBox("Acoes")
        a = QGridLayout(grp_acoes)
        botoes = [
            ("1. Abrir Ghidra (janela)", self.abrir_ghidra),
            ("2. Ghidra modo janela -> Codex", self.modo_janela),
            ("2b. Ghidra headless: escolher binario", self.modo_headless),
            ("3. Abrir Codex leve", lambda: abrir_terminal(["rea-codex"])),
            ("Baixar/preparar modelos", lambda: abrir_terminal(["rea-baixar-modelos"])),
            ("Atualizar ferramentas", lambda: abrir_terminal(["rea-atualizar"])),
            ("Verificar corte de prompt", self.verificar_corte),
            ("Liberar memoria (modelos)", self.liberar_memoria),
            ("Terminal", lambda: subprocess.Popen(["xterm", "-fa", "Monospace", "-fs", "11"])),
            ("Reiniciar", lambda: self.confirmar_energia("reboot")),
            ("Desligar", lambda: self.confirmar_energia("poweroff")),
        ]
        for i, (texto, acao) in enumerate(botoes):
            b = QPushButton(texto)
            b.setMinimumHeight(34)
            b.clicked.connect(acao)
            a.addWidget(b, i // 3, i % 3)
        raiz.addWidget(grp_acoes)

        # refinador
        grp_ref = QGroupBox("Refinar pseudocodigo do Ghidra -> C legivel (LLM4Decompile, CPU)")
        r = QVBoxLayout(grp_ref)
        caixas = QHBoxLayout()
        mono = QFont("Monospace", 9)
        self.txt_pseudo = QPlainTextEdit()
        self.txt_pseudo.setPlaceholderText("Cole aqui o pseudocodigo da janela Decompile do Ghidra")
        self.txt_pseudo.setFont(mono)
        self.txt_c = QPlainTextEdit()
        self.txt_c.setReadOnly(True)
        self.txt_c.setFont(mono)
        caixas.addWidget(self.txt_pseudo)
        caixas.addWidget(self.txt_c)
        r.addLayout(caixas)
        self.btn_ref = QPushButton("Refinar")
        self.btn_ref.clicked.connect(self.refinar)
        r.addWidget(self.btn_ref)
        raiz.addWidget(grp_ref, stretch=1)

        # mensagens
        self.saida = QPlainTextEdit()
        self.saida.setReadOnly(True)
        self.saida.setMaximumHeight(110)
        self.saida.setFont(mono)
        raiz.addWidget(self.saida)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.atualizar_status)
        self.timer.start(5000)
        self.atualizar_status()
        self.msg("Painel pronto. Ordem: modelos -> Ghidra (janela ou headless) -> Codex leve.")

    # --- utilidades ---
    def msg(self, texto: str):
        self.saida.appendPlainText(texto)

    @staticmethod
    def _cor(rotulo: QLabel, ok: bool, texto: str):
        rotulo.setText(texto)
        rotulo.setStyleSheet("color: #1b7f1b;" if ok else "color: #b22222;")

    # --- status ---
    def atualizar_status(self):
        v = ollama_get("/api/version")
        self._cor(self.lbl["ollama"], bool(v), f"Ollama: OK (v{v['version']})" if v else "Ollama: DESLIGADO")

        tags = ollama_get("/api/tags") or {}
        nomes = {m.get("name", "") for m in tags.get("models", [])}
        faltam = [m for m in (MODELO_AGENTE, MODELO_DECOMP) if m not in nomes]
        self._cor(self.lbl["modelos"], not faltam,
                  "Modelos: prontos" if not faltam else "Modelos faltando: " + ", ".join(faltam) + " (use 'Baixar modelos')")

        ps = ollama_get("/api/ps") or {}
        linhas = []
        for m in ps.get("models", []):
            total = m.get("size") or 0
            gpu = round(100 * (m.get("size_vram") or 0) / total) if total else 0
            linhas.append(f"{m.get('name')} {total / 2**30:.1f} GB, {gpu}% GPU")
        self.lbl["carregados"].setText("Carregados: " + ("; ".join(linhas) if linhas else "nenhum"))

        cfg = CODEX_CFG.read_text(encoding="utf-8") if CODEX_CFG.exists() else ""
        modo = modo_atual(cfg)
        if modo.startswith("headless"):
            self._cor(self.lbl["ghidra"], True, "Ghidra: headless (o Codex abre o binario sozinho)")
        else:
            aberto = porta_aberta(PORTA_GHIDRA)
            self._cor(self.lbl["ghidra"], aberto,
                      f"Ghidra porta {PORTA_GHIDRA}: PRONTO" if aberto
                      else f"Ghidra porta {PORTA_GHIDRA}: fechada (abra o binario no CodeBrowser)")
        self.lbl["modo"].setText(f"Modo Ghidra no Codex: {modo}")

        montado = os.path.ismount("/modelos")
        livre = shutil.disk_usage("/modelos" if os.path.isdir("/modelos") else "/").free / 2**30
        live = "boot=live" in Path("/proc/cmdline").read_text(errors="replace") if Path("/proc/cmdline").exists() else False
        persist = Path("/run/live/persistence").is_dir() and any(Path("/run/live/persistence").iterdir())
        if montado:
            local = "particao MODELOS"
        elif live:
            local = "pendrive com persistencia" if persist else "pendrive SEM persistencia (some ao desligar)"
        else:
            local = "no sistema"
        self._cor(self.lbl["disco"], (montado or persist or not live) and livre > 12,
                  f"/modelos: {local}, {livre:.0f} GB livres")

    # --- acoes ---
    def abrir_ghidra(self):
        subprocess.Popen(["ghidra"], cwd=str(Path.home()))
        self.msg("Ghidra abrindo. Depois: projeto > duplo clique no binario (CodeBrowser).")

    def _gravar_cfg(self, bloco: str):
        CODEX_CFG.parent.mkdir(parents=True, exist_ok=True)
        atual = CODEX_CFG.read_text(encoding="utf-8") if CODEX_CFG.exists() else ""
        if atual:
            shutil.copy2(CODEX_CFG, CODEX_CFG.with_suffix(".toml.bak"))
        CODEX_CFG.write_text(aplicar_bloco(atual, bloco), encoding="utf-8")

    def modo_janela(self):
        self._gravar_cfg(bloco_mcp("janela"))
        self.msg("Codex configurado: Ghidra com janela (porta 8080). Feche e reabra o Codex leve.")
        self.atualizar_status()

    def modo_headless(self):
        arq, _ = QFileDialog.getOpenFileName(self, "Escolha o binario para analisar", str(Path.home()))
        if not arq:
            return
        (PROJETOS / "ghidra").mkdir(parents=True, exist_ok=True)
        self._gravar_cfg(bloco_mcp("headless", arq))
        self.msg(f"Codex configurado: Ghidra headless com {arq}. "
                 "Abra o Codex leve; a 1a vez demora (importa e analisa o binario).")
        self.atualizar_status()

    def verificar_corte(self):
        cortes = cortes_no_log(LOG_OLLAMA)
        if cortes is None:
            self.msg(f"Log nao encontrado: {LOG_OLLAMA}")
        elif not cortes:
            self.msg("Nenhum corte de prompt registrado. O modelo esta vendo o pedido inteiro.")
        else:
            for hora, pr, lim in cortes:
                self.msg(f"CORTE {hora}: prompt={pr} tokens, limite={lim} (o modelo so viu o final)")

    def liberar_memoria(self):
        ps = ollama_get("/api/ps") or {}
        modelos = [m.get("name") for m in ps.get("models", [])]
        if not modelos:
            self.msg("Nenhum modelo carregado.")
            return
        for nome in modelos:
            try:
                ollama_post("/api/generate", {"model": nome, "keep_alive": 0}, timeout=30)
                self.msg(f"Descarregado: {nome}")
            except Exception as e:  # noqa: BLE001
                self.msg(f"Falha ao descarregar {nome}: {e}")

    def confirmar_energia(self, acao: str):
        nome = "reiniciar" if acao == "reboot" else "desligar"
        if QMessageBox.question(self, "Confirmar", f"Deseja {nome} o computador?") == QMessageBox.Yes:
            subprocess.Popen(["systemctl", acao])

    def refinar(self):
        pseudo = self.txt_pseudo.toPlainText().strip()
        if not pseudo:
            self.msg("Cole o pseudocodigo na caixa da esquerda primeiro.")
            return
        self.btn_ref.setEnabled(False)
        self.txt_c.setPlainText("Processando na CPU (30-90 s)...")
        self._thread = QThread(self)
        self._worker = Refinador(pseudo)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.executar)
        self._worker.pronto.connect(self._ref_ok)
        self._worker.erro.connect(self._ref_erro)
        self._worker.pronto.connect(self._thread.quit)
        self._worker.erro.connect(self._thread.quit)
        self._thread.start()

    def _ref_ok(self, texto: str):
        self.txt_c.setPlainText(texto)
        self.btn_ref.setEnabled(True)
        self.msg("Refinamento concluido.")

    def _ref_erro(self, erro: str):
        self.txt_c.setPlainText("")
        self.btn_ref.setEnabled(True)
        self.msg(f"Erro no refinamento: {erro}")


def main():
    app = QApplication(sys.argv)
    janela = Painel()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
