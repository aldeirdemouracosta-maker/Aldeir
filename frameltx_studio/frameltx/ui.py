"""Interface Gradio do FrameLTX Studio (estilo minimalista, inspirado no CapCut)."""

from __future__ import annotations

import html
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import gradio as gr

from . import __version__
from .backends import make_backend
from .config import AppConfig
from .jobs import Job, JobManager, JobStatus
from .pipelines import DURATIONS, MODES, GenerationRequest
from .presets import PRESETS, STYLES, load_custom_presets
from .storage import HistoryEntry, Storage
from .vram import PROFILES, GpuInfo, QualityProfile, detect_gpu, resolve_profile
from .workflows import describe_validation

log = logging.getLogger(__name__)

POLL_INTERVAL = 0.5

CSS = """
.gradio-container {max-width: 1280px !important; margin: auto;}
#brand h1 {font-size: 1.7rem; margin: 0;}
#brand p {opacity: .7; margin: .2rem 0 0;}
#gen-btn {min-height: 64px; font-size: 1.25rem; font-weight: 700; border-radius: 14px;
          background: linear-gradient(90deg, #ff2d6f, #7b5cff); color: white; border: none;}
#gen-btn:hover {filter: brightness(1.1);}
.pbar {height: 14px; border-radius: 7px; background: rgba(127,127,127,.25); overflow: hidden;}
.pbar > div {height: 100%; background: linear-gradient(90deg, #ff2d6f, #7b5cff);
             transition: width .4s ease;}
.pinfo {display: flex; justify-content: space-between; font-size: .9rem; margin-top: 6px; gap: 12px;}
.badge {display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: .8rem;
        background: rgba(123,92,255,.18); margin-right: 6px;}
"""


def progress_html(fraction: float, message: str) -> str:
    pct = int(round(max(0.0, min(fraction, 1.0)) * 100))
    return (
        f'<div class="pbar"><div style="width:{pct}%"></div></div>'
        f'<div class="pinfo"><span>{html.escape(message)}</span><b>{pct}%</b></div>'
    )


class StudioApp:
    """Estado da aplicação compartilhado entre os callbacks da interface."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.storage = Storage(cfg.output_dir)
        self.backend = make_backend(cfg)
        self.jobs = JobManager(self.backend, self.storage, cfg)
        self.gpu: GpuInfo | None = None
        load_custom_presets()
        self.refresh_gpu()

    # ---------- GPU / sistema ----------
    def refresh_gpu(self) -> None:
        self.gpu = detect_gpu(None if self.cfg.demo_mode else self.cfg.comfy_url)

    def profile_for(self, choice: str) -> QualityProfile:
        return resolve_profile("" if choice == "auto" else choice or self.cfg.force_profile, self.gpu)

    def header_badges(self) -> str:
        gpu = self.gpu.summary if self.gpu else "GPU não detectada"
        auto = self.profile_for("auto")
        backend = self.backend.name + (" (sem GPU)" if self.cfg.demo_mode else f" · {self.cfg.comfy_url}")
        return (
            f'<span class="badge">🎮 {html.escape(gpu)}</span>'
            f'<span class="badge">⚙️ Qualidade automática: {html.escape(auto.label)}</span>'
            f'<span class="badge">🔌 {html.escape(backend)}</span>'
        )

    def system_report(self) -> str:
        self.refresh_gpu()
        lines = ["### GPU"]
        if self.gpu:
            lines.append(f"- {self.gpu.summary}")
            if self.gpu.vram_total_gb < 6:
                lines.append("- ⚠️ Menos de 6 GB de VRAM: a geração pode falhar ou ser muito lenta.")
        else:
            lines.append("- ⚠️ Nenhuma GPU NVIDIA detectada. É necessário CUDA com 6 GB+ de VRAM.")
        lines += ["", "### Perfis de qualidade"]
        auto = self.profile_for("auto").key
        lines += [f"- {'👉 ' if p.key == auto else ''}{p.description}" for p in PROFILES]
        lines += ["", "### ComfyUI"]
        object_info = None
        if self.cfg.demo_mode:
            lines.append("- Modo demonstração ativo (`FRAMELTX_DEMO=1`): o ComfyUI não é usado.")
        else:
            client = getattr(self.backend, "client", None)
            if client and client.is_online():
                lines.append(f"- ✅ Online em {self.cfg.comfy_url}")
                try:
                    object_info = client.object_info()
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"- ⚠️ Não foi possível ler os nós instalados: {exc}")
            else:
                lines.append(f"- ❌ Offline em {self.cfg.comfy_url}. Inicie o ComfyUI e clique em Atualizar.")
        lines += ["", "### Workflows", describe_validation(self.cfg.workflows_dir, object_info)]
        lines += ["", f"### Pasta de saída\n- `{self.cfg.output_dir}`"]
        return "\n".join(lines)


# ======================================================================
# Callbacks
# ======================================================================

def _validate(mode: str, variant: str, start_image: str | None, prompt: str, preset: str) -> str | None:
    needs_image = mode in ("framepack", "combinado") or (mode == "ltx" and variant == "i2v")
    if needs_image and not start_image:
        return "Envie uma imagem inicial para este modo (ou use LTX Texto → Vídeo)."
    if mode == "ltx" and variant == "t2v" and not prompt.strip() and preset == "Livre":
        return "Escreva um prompt descrevendo o vídeo."
    return None


def _job_outputs(job: Job, last_preview_id: int | None) -> tuple[Any, ...]:
    """Converte o estado do job em atualizações dos componentes de saída."""
    preview_update = gr.update()
    if job.preview is not None and id(job.preview) != last_preview_id:
        preview_update = gr.update(value=job.preview, visible=True)
    video = file = gr.update()
    if job.status == JobStatus.DONE and job.result:
        video = gr.update(value=job.result.video_path)
        file = gr.update(value=job.result.video_path, visible=True)
    return (
        progress_html(job.progress, job.message),
        preview_update,
        video,
        file,
        "\n".join(job.logs[-40:]),
    )


def build_ui(app: StudioApp) -> gr.Blocks:
    profile_choices = [("Automático (pela VRAM)", "auto")] + [(p.label, p.key) for p in PROFILES]

    with gr.Blocks(title="FrameLTX Studio", css=CSS, theme=gr.themes.Soft(primary_hue="pink")) as demo:
        job_id = gr.State("")

        with gr.Row(elem_id="brand"):
            gr.Markdown(f"# 🎬 FrameLTX Studio\nVídeos curtos 9:16 com IA, 100% local · v{__version__}")
        badges = gr.HTML(app.header_badges())

        with gr.Tabs():
            # ------------------------------------------------------ Criar
            with gr.Tab("✨ Criar"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=5):
                        mode = gr.Radio([(v, k) for k, v in MODES.items()], value="framepack", label="Modo")
                        variant = gr.Radio(
                            [("Texto → Vídeo", "t2v"), ("Imagem → Vídeo", "i2v")],
                            value="t2v", label="Tipo LTX", visible=False,
                        )
                        with gr.Row():
                            start_img = gr.Image(type="filepath", label="Imagem inicial", height=260)
                            end_img = gr.Image(type="filepath", label="Imagem final (opcional)", height=260)
                        with gr.Row():
                            preset = gr.Dropdown(list(PRESETS), value="Livre", label="Preset")
                            style = gr.Dropdown(list(STYLES), value="Realista", label="Estilo")
                        prompt = gr.Textbox(
                            label="Prompt de movimento", lines=3,
                            placeholder="Ex.: a mulher sorri e acena para a câmera, cabelo ao vento",
                        )
                        duration = gr.Radio([(f"{d}s", d) for d in DURATIONS], value=5, label="Duração")
                        with gr.Accordion("Avançado", open=False):
                            with gr.Row():
                                seed = gr.Number(value=-1, precision=0, label="Seed (-1 = aleatória)")
                                quality = gr.Dropdown(profile_choices, value="auto", label="Qualidade")
                            export_hd = gr.Checkbox(value=True, label="Exportar em 1080×1920 (upscale)")
                        gen_btn = gr.Button("🎬 Gerar Vídeo", elem_id="gen-btn", variant="primary")
                        cancel_btn = gr.Button("Cancelar geração", variant="secondary", size="sm")
                        hint = gr.Markdown("")

                    with gr.Column(scale=4):
                        progress = gr.HTML(progress_html(0, "Pronto para gerar"))
                        preview = gr.Image(label="Prévia em tempo real", visible=False, height=320,
                                           interactive=False)
                        video = gr.Video(label="Resultado", height=480, interactive=False)
                        download = gr.File(label="Download MP4 9:16", visible=False, interactive=False)
                        logs = gr.Textbox(label="Log", lines=6, max_lines=12, interactive=False)

            # ------------------------------------------------------ Histórico
            with gr.Tab("🕘 Histórico") as hist_tab:
                with gr.Row():
                    hist_refresh = gr.Button("Atualizar", size="sm")
                    hist_delete = gr.Button("Apagar selecionado", size="sm", variant="stop")
                hist_ids = gr.State([])
                hist_selected = gr.State("")
                with gr.Row():
                    gallery = gr.Gallery(label="Gerações", columns=4, height=520, allow_preview=False)
                    with gr.Column():
                        hist_video = gr.Video(label="Vídeo", height=420, interactive=False)
                        hist_info = gr.Markdown("Selecione uma geração.")
                        hist_file = gr.File(label="Download", interactive=False)

            # ------------------------------------------------------ Fila
            with gr.Tab("📋 Fila"):
                queue_refresh = gr.Button("Atualizar", size="sm")
                queue_table = gr.Dataframe(
                    headers=["Job", "Status", "Modo", "Duração", "Progresso", "Mensagem"],
                    interactive=False, wrap=True,
                )

            # ------------------------------------------------------ Sistema
            with gr.Tab("🖥️ Sistema"):
                sys_refresh = gr.Button("Atualizar / detectar GPU novamente", size="sm")
                sys_report = gr.Markdown("Clique em atualizar para verificar GPU, ComfyUI e workflows.")

        # ================= eventos: formulário =================
        def on_mode(m: str) -> tuple[Any, Any]:
            return gr.update(visible=m == "ltx"), gr.update(visible=m != "ltx")

        mode.change(on_mode, mode, [variant, end_img])

        def on_preset(name: str) -> tuple[Any, str]:
            p = PRESETS[name]
            tip = f"💡 Modo recomendado: **{MODES[p.recommended_mode]}**" if name != "Livre" else ""
            if p.post_fps:
                tip += f" · resultado reamostrado para {p.post_fps} fps"
            return gr.update(value=p.recommended_style), tip

        preset.change(on_preset, preset, [style, hint])

        # ================= eventos: geração =================
        def generate(
            m: str, var: str, s_img: str | None, e_img: str | None, pset: str, sty: str,
            text: str, dur: int, sd: float, qual: str, hd: bool,
        ) -> Iterator[tuple[Any, ...]]:
            if err := _validate(m, var, s_img, text, pset):
                gr.Warning(err)
                yield (progress_html(0, err), gr.update(), gr.update(), gr.update(), gr.update(), "")
                return
            request = GenerationRequest(
                mode=m, prompt=text or "", preset=pset, style=sty, duration_s=int(dur),
                ltx_variant=var, start_image=Path(s_img) if s_img else None,
                end_image=Path(e_img) if e_img and m != "ltx" else None,
                seed=int(sd if sd is not None else -1), export_hd=hd,
            )
            job = app.jobs.submit(request, app.profile_for(qual))
            yield (progress_html(0, "Na fila…"), gr.update(visible=False, value=None),
                   gr.update(value=None), gr.update(visible=False, value=None), "", job.id)

            last_preview: int | None = None
            while True:
                pos = app.jobs.position(job.id)
                if pos > 0:
                    job.message = f"⏳ Na fila — posição {pos}"
                outputs = _job_outputs(job, last_preview)
                if job.preview is not None:
                    last_preview = id(job.preview)
                yield (*outputs, job.id)
                if job.finished:
                    if job.status == JobStatus.FAILED:
                        gr.Warning(job.error or "Falha na geração")
                    return
                time.sleep(POLL_INTERVAL)

        gen_event = gen_btn.click(
            generate,
            [mode, variant, start_img, end_img, preset, style, prompt, duration, seed, quality, export_hd],
            [progress, preview, video, download, logs, job_id],
            concurrency_limit=None,  # cada aba só acompanha seu job; quem serializa é a fila
        )

        def cancel(jid: str) -> None:
            if jid:
                app.jobs.cancel(jid)
                gr.Info("Cancelando…")

        cancel_btn.click(cancel, job_id, None)

        # ================= eventos: histórico =================
        def load_history() -> tuple[list[tuple[str, str]], list[str]]:
            entries = app.storage.load_history()
            items = [(e.thumbnail_path or e.video_path, e.label) for e in entries]
            return items, [e.id for e in entries]

        def entry_markdown(e: HistoryEntry) -> str:
            notes = "\n".join(f"- {n}" for n in e.notes)
            return (
                f"**{e.label}**\n\n**Prompt:** {e.prompt or '—'}\n\n"
                f"Preset: {e.preset} · Estilo: {e.style} · Perfil: {e.profile} · "
                f"Seed: `{e.seed}` · Tempo: {e.elapsed_s:.0f}s\n\n`{e.video_path}`"
                + (f"\n\n**Avisos:**\n{notes}" if notes else "")
            )

        def select_entry(ids: list[str], evt: gr.SelectData) -> tuple[Any, str, Any, str]:
            entries = {e.id: e for e in app.storage.load_history()}
            entry = entries.get(ids[evt.index]) if evt.index < len(ids) else None
            if not entry:
                return None, "Geração não encontrada.", None, ""
            return entry.video_path, entry_markdown(entry), entry.video_path, entry.id

        def delete_entry(selected: str) -> tuple[Any, ...]:
            if selected:
                app.storage.delete_entry(selected)
                gr.Info("Geração apagada.")
            items, ids = load_history()
            return items, ids, None, "Selecione uma geração.", None, ""

        hist_outputs = [gallery, hist_ids]
        demo.load(load_history, None, hist_outputs)
        gen_event.then(load_history, None, hist_outputs)  # nova geração aparece no histórico
        hist_tab.select(load_history, None, hist_outputs)
        hist_refresh.click(load_history, None, hist_outputs)
        gallery.select(select_entry, hist_ids, [hist_video, hist_info, hist_file, hist_selected])
        hist_delete.click(
            delete_entry, hist_selected,
            [gallery, hist_ids, hist_video, hist_info, hist_file, hist_selected],
        )

        # ================= eventos: fila e sistema =================
        def queue_rows() -> list[list[Any]]:
            return [
                [j.id, j.status.value, j.request.mode, f"{j.request.duration_s}s",
                 f"{int(j.progress * 100)}%", j.message]
                for j in app.jobs.recent(20)
            ]

        queue_refresh.click(queue_rows, None, queue_table)

        def system() -> tuple[str, str]:
            report = app.system_report()
            return report, app.header_badges()

        sys_refresh.click(system, None, [sys_report, badges])

    return demo


def launch(cfg: AppConfig) -> None:
    app = StudioApp(cfg)
    demo = build_ui(app)
    demo.queue(default_concurrency_limit=4, max_size=64)
    log.info("Abrindo interface em http://%s:%d", cfg.server_host, cfg.server_port)
    demo.launch(
        server_name=cfg.server_host, server_port=cfg.server_port, inbrowser=True,
        allowed_paths=[str(cfg.output_dir)],
    )

