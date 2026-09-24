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
  C              assistente de prompts: conversa, ficha ao lado e prompt pronto para
                 Wan2.2, VACE ou LTX (Qwen local se houver; senão, perguntas guiadas)
  U              atualizações: consulta GitHub/GitLab/Codeberg/Hugging Face, instala
                 ferramentas na partição de dados (sha256, teste, troca atômica) e reverte
  A              agentes e onde cada um roda (CPU, Vulkan, CUDA)
  M              modelos: recomendados, instalados e catálogo (sem downloads)
  G              sensores da GPU (Safety Guard, somente leitura)
  D              diagnóstico completo da máquina
  N              nova pasta
  R              atualiza a lista e redetecta agentes
  S              abre um shell (digite 'exit' para voltar)
  F1 ou ?        esta ajuda
  Q              sair

Pastas: Projetos, Midia (entrada), Modelos (pesos), Ferramentas (versões
instaladas pela tecla U), Saidas (resultados), Jobs (arquivos intermediários)
e Logs (JSONL por job).
Nada é executado sem confirmação. Recurso indisponível sempre mostra o motivo."""


TECLAS = [("F1", "Ajuda"), ("T", "Prompt"), ("C", "Assistente"), ("U", "Atualizar"), ("P", "Prévia"),
          ("I", "Info"), ("A", "Agentes"), ("M", "Modelos"), ("G", "GPU"), ("D", "Diag"), ("N", "Pasta"),
          ("Q", "Sair")]
DESCARTAR = ["N", "D", "G", "M", "A", "I", "P"]  # ordem em que saem da barra quando falta largura


def barra_de_teclas(largura: int) -> str:
    """Mostra o máximo de teclas que couber; Ajuda, Prompt, Assistente, Atualizar e Sair ficam sempre."""
    itens = list(TECLAS)
    for sep in ("  ", " "):
        texto = " " + sep.join(f"{k} {v}" for k, v in itens)
        if len(texto) <= largura - 1:
            return texto
    for k in DESCARTAR:
        itens = [t for t in itens if t[0] != k]
        texto = " " + " ".join(f"{a} {b}" for a, b in itens)
        if len(texto) <= largura - 1:
            return texto
    return texto


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
        self.servidor = None  # llama-server iniciado pelo assistente (/llm)
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
        self.put(h - 1, 0, barra_de_teclas(w), self.c["title"], w)
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

    def prompt_terminal(self, pedido: Optional[str] = None) -> None:
        """Pedido → Diretor, Editor e Fiscal (JSON validado) → plano explicado → confirmação."""
        from minivideo_agents.cli import _resumo_especialistas
        from minivideo_especialistas import pipeline
        e = self.b.selected
        entrada = e.path if e and e.kind == "vídeo" else None
        if pedido is None:
            pedido = self.ask("Terminal de prompt - descreva a edição (ex.: cena 1: 00:00:00 até 00:00:05 "
                              "limpe o áudio; cena 2: ...)")
        if not pedido:
            return
        self.msg = "Diretor, Editor e Fiscal planejando" + ELL
        self.draw()
        try:
            pl = pipeline.planejar(pedido, entrada, "auto", self.ws)
        except Exception as exc:  # plano inválido: mostra o motivo, nunca executa
            self.msg = "Plano recusado (nada foi executado)."
            self.text_view("Plano", f"Não foi possível planejar: {exc}")
            return
        self.msg = f"Plano {pl.job_id} pronto (nada foi executado)."
        self.draw()
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

    # ---------- assistente de prompts (C) ----------
    def _cliente_llm(self):
        from minivideo_especialistas.llm import ClienteLLM, LLMIndisponivel
        try:
            if self.servidor:
                return ClienteLLM(url=self.servidor.url, modelo="local", timeout=120)
            return ClienteLLM(timeout=120)
        except LLMIndisponivel:
            return None

    def _pasta_projeto(self) -> str:
        rel = self.b.relative_cwd
        if rel.startswith("Projetos" + os.sep):
            return self.b.cwd
        return os.path.join(self.ws.path("Projetos"), "geral")

    def _iniciar_llm(self) -> str:
        from minivideo_prompts.servidor import ServidorLocal, achar_gguf
        if self.servidor:
            return "O LLM local já está ligado."
        gguf = achar_gguf(self.ws.path("Modelos"))
        if not gguf:
            return ("Nenhum .gguf em Modelos/llm (ex.: Qwen3-1.7B). Veja a tecla M; sem ele o assistente "
                    "continua com perguntas guiadas.")
        if not shutil.which("llama-server"):
            return "llama-server ausente neste sistema."
        self.msg = f"Carregando {os.path.basename(gguf)} no llama-server" + ELL
        self.draw()
        srv = ServidorLocal(gguf)
        try:
            srv.iniciar(os.path.join(self.ws.logs, "llama-server.log"))
        except RuntimeError as exc:
            return f"Não foi possível ligar o LLM: {exc}"
        self.servidor = srv
        self.msg = ""
        return f"LLM local ligado ({os.path.basename(gguf)}). As próximas falas usam o Qwen."

    def _desenhar_assistente(self, conv, entrada: str, aviso: str) -> None:
        from minivideo_prompts import modelos, vocabulario as voc
        h, w = self.scr.getmaxyx()
        top, bottom = 1, h - 3
        motor = "Qwen local" if conv.llm_ativo else "perguntas guiadas"
        self.put(top, 0, f" Assistente de prompts {DASH} {modelos.MODELOS[conv.modelo]['nome']} {DASH} "
                         f"motor: {motor}", self.c["title"], w)
        lw = max(30, (w * 3) // 5)
        rw = w - lw - 1
        # conversa (esquerda): as últimas linhas que couberem
        linhas: List[str] = []
        for fala in conv.dialogo:
            quem = "Você: " if fala["papel"] == "usuario" else "Assistente: "
            for i, para in enumerate(fala["texto"].splitlines() or [""]):
                pre = quem if i == 0 else "  "
                linhas += textwrap.wrap(pre + para, lw - 2) or [""]
            linhas.append("")
        area = bottom - top - 2
        for i, ln in enumerate(linhas[-area:] if len(linhas) > area else linhas):
            self.put(top + 1 + i, 0, " " + ln, self.c["win"], lw)
        for y in range(top + 1 + min(len(linhas), area), bottom - 1):
            self.put(y, 0, "", self.c["win"], lw)
        # ficha e prompt (direita)
        x = lw + 1
        lado = [("Ficha do vídeo", True)]
        for campo in voc.ORDEM:
            val = conv.ficha.get(campo) or ("(pulado)" if campo in conv.pulados else "-")
            lado.append((f"{campo:<10} {val}", False))
        if conv.ficha.get("assunto"):
            r = modelos.montar(conv.ficha, conv.modelo)
            lado += [("", False), ("Prompt", True)]
            lado += [(ln, False) for ln in textwrap.wrap(r["prompt"], rw - 2)]
            p = r["parametros"]
            lado.append((f"{p['tamanho']} · {p['fps']} fps · {p['quadros']} quadros", False))
        for i in range(bottom - top - 2):
            txt, titulo = lado[i] if i < len(lado) else ("", False)
            self.put(top + 1 + i, x, " " + txt, self.c["dim"] if titulo else self.c["win"], rw)
        # entrada e ajuda
        vis = entrada[-(w - 6):]
        self.put(bottom - 1, 0, " > " + vis, self.c["sel"], w)
        dica = aviso or ("Enter envia · /pronto /salvar /enviar /refinar /llm /modelo /ficha /novo · Esc sai")
        self.put(bottom, 0, " " + dica, self.c["bar"], w)
        self.scr.move(bottom - 1, min(3 + len(vis), w - 2))
        self.scr.refresh()

    def assistente(self) -> None:
        from minivideo_especialistas.llm import LLMIndisponivel
        from minivideo_especialistas.schema import SchemaError
        from minivideo_prompts.conversa import Conversa, salvar
        conv = Conversa(cliente=self._cliente_llm())
        conv.abrir()
        buf: List[str] = []
        aviso = ""
        curses.curs_set(1)
        try:
            while True:
                self._desenhar_assistente(conv, "".join(buf), aviso)
                try:
                    ch = self.scr.get_wch()
                except curses.error:
                    continue
                if ch == "\x1b":
                    return
                if ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if buf:
                        buf.pop()
                    continue
                if isinstance(ch, str) and ch.isprintable():
                    buf.append(ch)
                    continue
                if ch not in ("\n", "\r", curses.KEY_ENTER):
                    continue
                texto, buf, aviso = "".join(buf).strip(), [], ""
                cmd = texto.split()[0].lower() if texto.startswith("/") else ""
                if cmd == "/llm":
                    conv.dialogo.append({"papel": "usuario", "texto": texto})
                    conv.dialogo.append({"papel": "assistente", "texto": self._iniciar_llm()})
                    conv.cliente = self._cliente_llm()
                    continue
                if cmd in ("/salvar", "/enviar", "/refinar"):
                    if not conv.ficha.get("assunto"):
                        aviso = "Descreva o vídeo primeiro."
                        continue
                    try:
                        if cmd == "/refinar":
                            self._desenhar_assistente(conv, "", "Refinando com o LLM local" + ELL)
                        doc = conv.resultado(refinar=(cmd == "/refinar"))
                    except (LLMIndisponivel, SchemaError) as exc:
                        aviso = f"Não foi possível: {exc}"
                        continue
                    if cmd == "/refinar":
                        conv.dialogo.append({"papel": "assistente", "texto": "Refinado (inglês):\n" + doc["prompt"]})
                        self._refinado = doc
                        continue
                    doc = getattr(self, "_refinado", None) if getattr(self, "_refinado", None) and \
                        self._refinado.get("ficha") == conv.ficha else doc
                    if cmd == "/salvar":
                        caminho = salvar(doc, self._pasta_projeto())
                        self.b.refresh()
                        aviso = f"Salvo em {os.path.relpath(caminho, self.ws.root)}"
                        continue
                    curses.curs_set(0)
                    self.prompt_terminal("gere um vídeo: " + doc["prompt"])
                    curses.curs_set(1)
                    continue
                if texto:
                    self._desenhar_assistente(conv, "", "Pensando" + ELL)
                    try:
                        conv.responder(texto)
                    except LLMIndisponivel as exc:
                        aviso = f"LLM indisponível: {exc}"
        finally:
            self._refinado = None
            curses.curs_set(0)

    # ---------- atualizações (U) ----------
    def atualizacoes(self) -> None:
        from minivideo_atualizacoes import forjas, indice, instalador
        from minivideo_atualizacoes.cli import linhas_indice
        sel, aviso = 0, ""
        while True:
            doc = indice.ler_indice(self.ws.root)
            itens = doc["itens"] if doc else []
            h, w = self.scr.getmaxyx()
            top, bottom = 1, h - 3
            self.put(top, 0, " Atualizações " + DASH + (f" índice de {doc['consultado_em']}" if doc else
                                                          " sem índice: aperte V para consultar"), self.c["title"], w)
            linhas = linhas_indice(doc)[1:] if doc else [
                "Nada foi consultado ainda. V consulta os repositórios acompanhados (GitHub, GitLab,",
                "Codeberg/Forgejo, Hugging Face) e mostra o que há de novo. Nada é instalado sem você confirmar."]
            sel = min(sel, max(len(itens) - 1, 0))
            area = bottom - top - 7
            ini = max(0, sel - area + 1)
            for i in range(area):
                j = ini + i
                txt = linhas[j] if j < len(linhas) else ""
                attr = self.c["sel"] if (itens and j == sel) else self.c["win"]
                self.put(top + 1 + i, 0, " " + txt, attr, w)
            # detalhes do item selecionado
            det = []
            if itens:
                it = itens[sel]
                det.append(f"{it['id']} · {it['forja']}:{it['repo']} · {it['tipo']}")
                det.append(f"página: {it.get('pagina') or '-'}   publicado: {it.get('data') or '-'}")
                if it.get("arquivo"):
                    a = it["arquivo"]
                    det.append(f"arquivo: {a['nome']} · sha256: {a['sha256'] or 'não publicado'}")
                nota = " ".join((it.get("notas") or "").split())
                det.append("notas: " + (nota[:w * 2] or "-"))
            for i in range(6):
                self.put(bottom - 6 + i, 0, " " + (det[i] if i < len(det) else ""), self.c["dim"], w)
            self.put(bottom, 0, " " + (aviso or "V consultar · Enter instalar · R reverter · H histórico · Esc sai"),
                     self.c["bar"], w)
            self.scr.refresh()
            ch = self.scr.getch()
            if ch == -1:
                continue
            aviso = ""
            if ch in (27, ord("q")):
                return
            if ch in (curses.KEY_DOWN, ord("j")):
                sel += 1
            elif ch in (curses.KEY_UP, ord("k")):
                sel = max(sel - 1, 0)
            elif ch in (ord("v"), ord("V")):
                self.put(bottom, 0, " Consultando os repositórios" + ELL, self.c["bar"], w)
                self.scr.refresh()
                d = indice.atualizar_indice(self.ws.root)
                novos = sum(1 for i in d["itens"] if i["novo"])
                erros = sum(1 for i in d["itens"] if i.get("erro") and not i.get("disponivel"))
                aviso = f"{novos} novidade(s)" + (f", {erros} fonte(s) com erro (rede?)" if erros else "")
            elif ch in (ord("h"), ord("H")):
                hist = instalador.historico(self.ws.root)
                self.text_view("Histórico de atualizações", "\n".join(
                    " · ".join(f"{k}={v}" for k, v in e.items()) for e in hist) or "(vazio)")
            elif ch in (ord("r"), ord("R")) and itens:
                try:
                    para = instalador.reverter(self.ws.root, itens[sel]["id"])
                    aviso = f"{itens[sel]['id']}: agora usando {para}"
                    self._assign = None
                except instalador.Recusado as exc:
                    aviso = str(exc)
            elif ch in (10, 13, curses.KEY_ENTER) and itens:
                it = itens[sel]
                item = next((f for f in indice.carregar_fontes(self.ws.root) if f["id"] == it["id"]), None)
                if not item:
                    continue
                if not it.get("novo"):
                    aviso = f"{it['id']}: nada novo para instalar."
                    continue
                sem_hash = bool(it.get("arquivo")) and not it["arquivo"].get("sha256")
                pergunta = f"Instalar {it['id']} {it['disponivel']}? (s/N)"
                if sem_hash:
                    pergunta = f"{it['id']}: a plataforma NÃO publicou sha256. Instalar mesmo assim? (s/N)"
                resp = self.ask(pergunta)
                if not resp or resp.lower() not in ("s", "sim"):
                    aviso = "Cancelado."
                    continue
                self.put(bottom, 0, " Baixando, conferindo e testando" + ELL, self.c["bar"], w)
                self.scr.refresh()
                try:
                    v = instalador.aplicar(self.ws.root, item, it, aceitar_sem_hash=sem_hash)
                    instalador.ativar_path(self.ws.root)
                    self._assign = None
                    aviso = f"{it['id']} {v} ativo. R volta para a versão anterior."
                except (instalador.Recusado, forjas.ErroFonte) as exc:
                    aviso = f"Recusado: {exc}"

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
            elif ch in (ord("c"), ord("C")):
                self.assistente()
            elif ch in (ord("u"), ord("U")):
                self.atualizacoes()
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
    from minivideo_atualizacoes.instalador import ativar_path
    ativar_path(ws.root)  # ferramentas atualizadas (tecla U) vêm antes das do ISO

    def rodar(scr):
        app = App(scr, ws)
        try:
            app.run()
        finally:
            if app.servidor:
                app.servidor.parar()

    curses.wrapper(rodar)
    return 0
