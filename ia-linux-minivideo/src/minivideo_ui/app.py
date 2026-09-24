"""Interface de pastas do IA-Linux MiniVideo (curses, só teclado).

Roda no console do ISO (tty1) e em qualquer terminal Linux. Visual
inspirado no Windows 98 (área teal, janelas cinza-claro, barra de título
azul) com alto contraste e foco sempre visível (item em destaque invertido).
"""

from __future__ import annotations

import curses
import os
import shutil
import subprocess
import textwrap
import threading
import time
from typing import List, Optional

from minivideo_agents import devices as devmod
from minivideo_agents.executor import probe
from minivideo_agents.registry import route_all
from minivideo_agents.workspace import Workspace
from minivideo_audit import audit
from minivideo_guard.policy import GuardPolicy
from minivideo_guard.sensors import AmdgpuSysfsBackend

from .model import Browser, human_size

TOOL_DIRS = ["/usr/libexec/minivideo"]
# O console Linux (fonte lat1-16 no ISO) tem acentos, mas não ◄ — … : usa ASCII.
_CONSOLE = os.environ.get("TERM") == "linux"
FOCUS, DASH, ELL = (" <", "-", "...") if _CONSOLE else (" ◄", "—", "…")
_ASCII = str.maketrans({"—": "-", "–": "-", "…": "...", "◄": "<", "→": "->", "≥": ">=", "≤": "<=", "°": "o"})
HELP = """Teclas

  Tab            alterna entre Pastas e Arquivos
  Setas / PgUp / PgDn   move a seleção
  Enter          abre a pasta (ou mostra informações do arquivo)
  Backspace / Esc   volta para a pasta anterior
  P              prévia do vídeo (mpv; no console usa a saída DRM)
  I              informações do arquivo (ffprobe)
  T              terminal de prompt: Diretor, Editor e Fiscal planejam; você confirma;
                 o Continuísta confere o resultado
  A              agentes e onde cada um roda (CPU, Vulkan, CUDA)
  M              modelos: recomendados, instalados e catálogo (sem downloads)
  G              sensores da GPU (Safety Guard, somente leitura)
  D              diagnóstico completo da máquina
  N              nova pasta
  R              atualiza a lista e redetecta agentes
  S              abre um shell (digite 'exit' para voltar)
  F1 ou ?        esta ajuda
  Q              sair

Pastas: Projetos, Midia (entrada), Modelos (pesos), Saidas (resultados),
Jobs (arquivos intermediários) e Logs (JSONL por job).
Nada é executado sem confirmação. Recurso indisponível sempre mostra o motivo."""


class App:
    def __init__(self, scr, ws: Workspace):
        self.scr = scr
        self.ws = ws
        self.b = Browser(ws)
        self.msg = ""
        self.gpu_text = "GPU: lendo" + ELL
        self.gpu_at = 0.0
        self.policy = GuardPolicy()
        self.job_thread: Optional[threading.Thread] = None
        self.job_status = ""
        self._assign = None
        self._init_colors()

    # ---------- aparência ----------
    def _init_colors(self) -> None:
        self.c = {k: curses.A_NORMAL for k in ("desk", "win", "title", "sel", "bar", "warn", "dim")}
        if os.environ.get("MINIVIDEO_UI_MONO") or not curses.has_colors():
            self.c.update(title=curses.A_REVERSE | curses.A_BOLD, sel=curses.A_REVERSE, bar=curses.A_REVERSE,
                          warn=curses.A_BOLD)
            return
        curses.start_color()
        pairs = {"desk": (curses.COLOR_BLACK, curses.COLOR_CYAN), "win": (curses.COLOR_BLACK, curses.COLOR_WHITE),
                 "title": (curses.COLOR_WHITE, curses.COLOR_BLUE), "sel": (curses.COLOR_WHITE, curses.COLOR_BLUE),
                 "bar": (curses.COLOR_BLACK, curses.COLOR_WHITE), "warn": (curses.COLOR_WHITE, curses.COLOR_RED),
                 "dim": (curses.COLOR_BLUE, curses.COLOR_WHITE)}
        for i, (k, (fg, bg)) in enumerate(pairs.items(), 1):
            curses.init_pair(i, fg, bg)
            self.c[k] = curses.color_pair(i)
        self.c["title"] |= curses.A_BOLD
        self.c["sel"] |= curses.A_BOLD

    def put(self, y: int, x: int, text: str, attr=0, width: Optional[int] = None) -> None:
        if _CONSOLE:
            text = text.translate(_ASCII)
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        width = min(width if width is not None else len(text), w - x - (1 if y == h - 1 else 0))
        if width <= 0:
            return
        try:
            self.scr.addstr(y, x, text[:width].ljust(width), attr)
        except curses.error:
            pass

    # ---------- dados vivos ----------
    def assignments(self):
        if self._assign is None:
            devs = devmod.detect()
            self._assign = {a.agent.id: a for a in route_all(devs, self.ws.models_dirs, TOOL_DIRS)}
        return self._assign

    def update_gpu(self) -> None:
        if time.time() - self.gpu_at < 2:
            return
        self.gpu_at = time.time()
        backend = AmdgpuSysfsBackend()
        devs = backend.discover()
        if not devs:
            self.gpu_text = "GPU: sem sensores"
            return
        r = backend.read(devs[0])
        d = self.policy.evaluate(r)
        t = r.metrics["temp_edge_c"]
        self.gpu_text = f"{devs[0].id} {'n/d' if t is None else f'{t:.0f}°C'} {d.name}"

    # ---------- desenho ----------
    def draw(self) -> None:
        self.update_gpu()
        h, w = self.scr.getmaxyx()
        self.scr.erase()
        for y in range(h):
            self.put(y, 0, "", self.c["desk"], w)
        if h < 12 or w < 50:
            self.put(0, 0, "Janela pequena demais (mínimo 50x12).", self.c["warn"])
            self.scr.refresh()
            return
        gpu = f" {self.gpu_text} "
        room = w - len(gpu) - 1
        root = self.ws.root if len(self.ws.root) <= room - 24 else ELL + self.ws.root[-(room - 27):]
        self.put(0, 0, f" IA-Linux MiniVideo {DASH} {root} ", self.c["title"], room)
        self.put(0, room, gpu, self.c["title"], w - room)

        left_w = 16
        top, bottom = 1, h - 3
        # painel de pastas
        focus_l = self.b.pane == "pastas"
        self.put(top, 0, " Pastas" + (FOCUS if focus_l else ""), self.c["title"] if focus_l else self.c["dim"], left_w)
        for i, f in enumerate(self.b.folders):
            y = top + 1 + i
            if y >= bottom:
                break
            active = i == self.b.folder_idx
            attr = self.c["sel"] if (active and focus_l) else (self.c["win"] | curses.A_BOLD if active else self.c["win"])
            self.put(y, 0, (" > " if active else "   ") + f, attr, left_w)
        for y in range(top + 1 + len(self.b.folders), bottom):
            self.put(y, 0, "", self.c["win"], left_w)

        # painel de arquivos
        x = left_w + 1
        fw = w - x
        focus_r = not focus_l
        head = f" {self.b.relative_cwd}" + (FOCUS if focus_r else "")
        self.put(top, x, head, self.c["title"] if focus_r else self.c["dim"], fw)
        rows = bottom - top - 1
        start = max(0, self.b.sel - rows + 1) if focus_r else 0
        visible = self.b.entries[start:start + rows]
        for i in range(rows):
            y = top + 1 + i
            if i < len(visible):
                e = visible[i]
                idx = start + i
                name = e.name + ("/" if e.is_dir else "")
                line = f" {name[:fw - 24]:<{max(fw - 24, 1)}} {human_size(e.size):>9}  {e.kind:<8}"
                attr = self.c["sel"] if (focus_r and idx == self.b.sel) else self.c["win"]
                self.put(y, x, line, attr, fw)
            elif i == 0 and not self.b.entries:
                self.put(y, x, "  (pasta vazia)", self.c["win"], fw)
            else:
                self.put(y, x, "", self.c["win"], fw)

        # barra de estado e atalhos
        status = self.job_status or self.msg
        if not self.ws.persistent:
            status = (status + "  |  " if status else "") + "Sem partição MV_DADOS: arquivos em RAM somem ao desligar"
            self.put(h - 2, 0, " " + status, self.c["warn"], w)
        else:
            self.put(h - 2, 0, " " + (status or "Pronto."), self.c["bar"], w)
        keys = " F1 Ajuda  T Prompt  P Prévia  I Info  A Agentes  M Modelos  G GPU  D Diag  N Pasta  Q Sair"
        self.put(h - 1, 0, keys, self.c["title"], w)
        self.scr.refresh()

    # ---------- diálogos ----------
    def text_view(self, title: str, text: str, footer: str = "Esc/Enter fecha · Setas rolam",
                  keys: str = "") -> int:
        """Mostra texto rolável. Devolve a tecla que fechou (Esc, Enter ou uma de ``keys``)."""
        pos = 0
        while True:
            h, w = self.scr.getmaxyx()
            lines: List[str] = []
            for para in text.splitlines():
                lines += textwrap.wrap(para, w - 6, replace_whitespace=False) or [""]
            box_h = h - 4
            self.put(1, 1, f" {title} ", self.c["title"], w - 2)
            for i in range(box_h - 2):
                ln = lines[pos + i] if pos + i < len(lines) else ""
                self.put(2 + i, 1, "  " + ln, self.c["win"], w - 2)
            self.put(box_h, 1, f" {footer} ", self.c["bar"], w - 2)
            self.scr.refresh()
            ch = self.scr.getch()
            if ch in (27, 10, 13, curses.KEY_ENTER, ord("q")):
                return ch
            if keys and 0 <= ch < 256 and chr(ch).lower() in keys:
                return ord(chr(ch).lower())
            if ch in (curses.KEY_DOWN, ord("j")):
                pos = min(pos + 1, max(len(lines) - (box_h - 2), 0))
            elif ch in (curses.KEY_UP, ord("k")):
                pos = max(pos - 1, 0)
            elif ch == curses.KEY_NPAGE:
                pos = min(pos + box_h - 2, max(len(lines) - (box_h - 2), 0))
            elif ch == curses.KEY_PPAGE:
                pos = max(pos - (box_h - 2), 0)

    def ask(self, label: str, initial: str = "") -> Optional[str]:
        """Linha de edição simples. Enter confirma, Esc cancela."""
        buf = list(initial)
        curses.curs_set(1)
        try:
            while True:
                h, w = self.scr.getmaxyx()
                y = h // 2
                self.put(y - 2, 2, f" {label} ", self.c["title"], w - 4)
                visible = "".join(buf)[-(w - 8):]
                self.put(y - 1, 2, "", self.c["win"], w - 4)
                self.put(y, 2, " > " + visible, self.c["win"], w - 4)
                self.put(y + 1, 2, " Enter confirma · Esc cancela ", self.c["bar"], w - 4)
                self.scr.move(y, min(5 + len(visible), w - 3))
                self.scr.refresh()
                try:
                    ch = self.scr.get_wch()
                except curses.error:  # tempo limite sem tecla
                    continue
                if ch in ("\n", "\r", curses.KEY_ENTER):
                    return "".join(buf).strip()
                if ch in ("\x1b",):
                    return None
                if ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if buf:
                        buf.pop()
                elif isinstance(ch, str) and ch.isprintable():
                    buf.append(ch)
        finally:
            curses.curs_set(0)

    # ---------- ações ----------
    def external(self, cmd: List[str]) -> int:
        curses.def_prog_mode()
        curses.endwin()
        try:
            return subprocess.call(cmd)
        except OSError as exc:
            self.msg = f"falha ao executar {cmd[0]}: {exc}"
            return 1
        finally:
            curses.reset_prog_mode()
            self.scr.refresh()

    def preview(self) -> None:
        e = self.b.selected
        if not e or e.kind not in ("vídeo", "áudio", "imagem"):
            self.msg = "Selecione um vídeo, áudio ou imagem na lista de arquivos."
            return
        if shutil.which("mpv"):
            vo = ["--vo=drm"] if os.environ.get("TERM") == "linux" else []
            self.external(["mpv", "--really-quiet", *vo, e.path])
        elif shutil.which("ffplay"):
            self.external(["ffplay", "-autoexit", "-loglevel", "error", e.path])
        else:
            self.msg = "Prévia indisponível: mpv e ffplay ausentes."

    def info(self) -> None:
        e = self.b.selected
        if not e or e.is_dir:
            self.msg = "Selecione um arquivo."
            return
        if not shutil.which("ffprobe"):
            self.text_view("Informações", f"{e.path}\n{human_size(e.size)}\n\nffprobe ausente: detalhes indisponíveis.")
            return
        try:
            p = probe(e.path)
        except Exception as exc:  # arquivo não é mídia
            self.text_view("Informações", f"{e.path}\n{human_size(e.size)}\n\nNão é mídia legível: {exc}")
            return
        v, a = p["video"], p["audio"]
        text = [e.path, f"Tamanho: {human_size(e.size)}", f"Duração: {p['duracao']:.2f} s"]
        if v:
            text.append(f"Vídeo: {v.get('codec_name')} {v.get('width')}x{v.get('height')} "
                        f"{(p['fps'] or 0):.2f} fps")
        text.append(f"Áudio: {a.get('codec_name')} {a.get('sample_rate')} Hz" if a else "Áudio: nenhum")
        self.text_view("Informações", "\n".join(text))

    def prompt_terminal(self) -> None:
        """Pedido → Diretor, Editor e Fiscal (JSON validado) → plano explicado → confirmação."""
        from minivideo_agents.cli import _resumo_especialistas
        from minivideo_especialistas import pipeline
        e = self.b.selected
        entrada = e.path if e and e.kind == "vídeo" else None
        pedido = self.ask("Terminal de prompt - descreva a edição (ex.: cena 1: 00:00:00 até 00:00:05 "
                          "limpe o áudio; cena 2: ...)")
        if not pedido:
            return
        self.msg = "Diretor, Editor e Fiscal planejando" + ELL
        self.draw()
        try:
            pl = pipeline.planejar(pedido, entrada, "auto", self.ws)
        except Exception as exc:  # plano inválido: mostra o motivo, nunca executa
            self.text_view("Plano", f"Não foi possível planejar: {exc}")
            return
        text = _resumo_especialistas(pl)
        if entrada:
            saida = self.b.default_output(entrada)
            text += f"\n\nEntrada: {entrada}\nSaída:   {saida}"
            footer = "E executar · Esc cancelar"
        else:
            text += "\n\nPara executar, selecione um vídeo na lista de arquivos antes de abrir o terminal."
            footer = "Esc fechar"
        ch = self.text_view("Plano dos especialistas (nada foi executado)", text, footer, keys="e")
        if ch == ord("e") and entrada:
            self.start_job(pl, saida)

    def start_job(self, plano, saida: str) -> None:
        from minivideo_especialistas import pipeline
        if self.job_thread and self.job_thread.is_alive():
            self.msg = "Já existe um job em execução."
            return

        def work():
            self.job_status = f"Executando job {plano.job_id}" + ELL + " (Logs/ e Jobs/ mostram cada etapa)"
            try:
                res = pipeline.executar(plano, saida, self.ws)
                if res["status"] == "concluido":
                    c = res.get("continuista") or {}
                    self.msg = f"Continuísta: {c.get('veredito', '?')} · concluído: {saida}"
                else:
                    self.msg = f"Falhou ({plano.job_id}): {res.get('erro')}"
            except pipeline.Recusado as exc:
                self.msg = f"Recusado: {exc}"
            finally:
                self.job_status = ""
                self.b.refresh()

        self.job_thread = threading.Thread(target=work, daemon=True)
        self.job_thread.start()

    def models_view(self) -> None:
        from minivideo_especialistas.fiscal import ram_disponivel_mib
        from minivideo_modelos import gerenciador as g
        linhas = ["Recomendados para esta máquina:"]
        for r in g.recomendar(devmod.detect(), ram_disponivel_mib()):
            linhas.append(f"  - {r['id'] or '(indisponível)'}: {r['porque']}")
        linhas += ["", "Em Modelos/:"]
        itens = g.inventario(self.ws.path("Modelos"))
        for it in itens:
            linhas.append(f"  {it.relativo} ({it.tamanho_mib:.1f} MiB, {it.formato}, {it.modelo or 'desconhecido'})")
            linhas += [f"      - {p}" for p in it.problemas]
        if not itens:
            linhas.append("  (vazio)")
        linhas += ["", "Catálogo (nada é baixado automaticamente; no shell: minivideo-modelos instrucoes <id>):"]
        for m in g.catalogo():
            linhas.append(f"  {m['id']:<18} {m['agente']:<18} requer {'/'.join(m['requer'])} · {m['licenca']}")
        self.text_view("Modelos", "\n".join(linhas))

    def agents_view(self) -> None:
        lines = []
        for a in self.assignments().values():
            dev = f"{a.device.id} ({a.device.kind})" if a.device else "nenhum"
            lines.append(f"{'[OK]' if a.disponivel else '[--]'} {a.agent.nome} — {a.agent.papel}")
            lines.append(f"      dispositivo: {dev} · {a.agent.estado}")
            lines += [f"      - {m}" for m in a.motivos]
        self.text_view("Agentes", "\n".join(lines))

    def gpu_view(self) -> None:
        backend = AmdgpuSysfsBackend()
        devs = backend.discover()
        if not devs:
            self.text_view("GPU", "Nenhuma GPU AMD com amdgpu encontrada em /sys/class/drm.")
            return
        out = []
        for d in devs:
            r = backend.read(d)
            out.append(f"{d.id} ({d.pci_device}, driver {d.driver})")
            for k, v in r.metrics.items():
                out.append(f"  {k:<16} {'indisponível' if v is None else f'{v:.1f}'}")
            out += [f"  aviso: {x}" for x in r.errors]
        self.text_view("GPU — somente leitura", "\n".join(out))

    def diag_view(self) -> None:
        self.msg = "Coletando diagnóstico…"
        self.draw()
        self.text_view("Diagnóstico", audit.render_text(audit.collect("/", self.ws.models_dirs)))
        self.msg = ""

    def new_folder(self) -> None:
        name = self.ask(f"Nova pasta em {self.b.relative_cwd}")
        if name:
            try:
                self.b.new_folder(name)
                self.b.pane = "arquivos"
                self.msg = f"Pasta criada: {name}"
            except (ValueError, OSError) as exc:
                self.msg = str(exc)

    # ---------- laço ----------
    def run(self) -> None:
        curses.curs_set(0)
        self.scr.keypad(True)
        self.scr.timeout(500)
        while True:
            self.draw()
            ch = self.scr.getch()
            if ch == -1:
                continue
            self.msg = ""
            if ch in (ord("q"), ord("Q")):
                if self.job_thread and self.job_thread.is_alive():
                    self.msg = "Há um job em execução; aguarde terminar."
                    continue
                return
            if ch == 9:
                self.b.toggle_pane()
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.b.move(1)
            elif ch in (curses.KEY_UP, ord("k")):
                self.b.move(-1)
            elif ch == curses.KEY_NPAGE:
                self.b.move(10)
            elif ch == curses.KEY_PPAGE:
                self.b.move(-10)
            elif ch == curses.KEY_RIGHT and self.b.pane == "pastas":
                self.b.toggle_pane()
            elif ch in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
                if self.b.enter() is not None:
                    self.info()
            elif ch in (curses.KEY_BACKSPACE, 127, 8, 27, curses.KEY_LEFT):
                self.b.back()
            elif ch in (curses.KEY_F1, ord("?")):
                self.text_view("Ajuda", HELP)
            elif ch in (ord("p"), ord("P")):
                self.preview()
            elif ch in (ord("i"), ord("I")):
                self.info()
            elif ch in (ord("t"), ord("T")):
                self.prompt_terminal()
            elif ch in (ord("a"), ord("A")):
                self.agents_view()
            elif ch in (ord("m"), ord("M")):
                self.models_view()
            elif ch in (ord("g"), ord("G")):
                self.gpu_view()
            elif ch in (ord("d"), ord("D")):
                self.diag_view()
            elif ch in (ord("n"), ord("N")):
                self.new_folder()
            elif ch in (ord("s"), ord("S")):
                self.external([os.environ.get("SHELL", "/bin/sh")])
            elif ch in (ord("r"), ord("R")):
                self.b.refresh()
                self._assign = None
                self.msg = "Lista e agentes atualizados."


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="minivideo-ui", description="Interface de pastas do IA-Linux MiniVideo.")
    p.add_argument("--workspace", help="pasta de trabalho (padrão: /data/minivideo ou ~/MiniVideo)")
    args = p.parse_args(argv)
    os.environ.setdefault("ESCDELAY", "25")
    ws = Workspace(args.workspace)
    curses.wrapper(lambda scr: App(scr, ws).run())
    return 0
