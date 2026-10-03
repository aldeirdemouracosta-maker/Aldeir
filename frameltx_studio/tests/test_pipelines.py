import time
from pathlib import Path

import pytest

from frameltx import video_utils as vu
from frameltx.backends import DemoBackend
from frameltx.comfy_client import ComfyOOMError
from frameltx.jobs import JobManager, JobStatus
from frameltx.pipelines import GenerationRequest, PipelineContext, UserFacingError, run_generation
from frameltx.storage import Storage
from frameltx.vram import PROFILE_BY_KEY


def make_ctx(cfg, backend=None, profile="baixo"):
    events = []
    ctx = PipelineContext(
        backend=backend or DemoBackend(step_delay=0), storage=Storage(cfg.output_dir), cfg=cfg,
        profile=PROFILE_BY_KEY[profile], emit=lambda f, m, p: events.append((f, m)),
    )
    return ctx, events


@pytest.mark.parametrize("mode,variant,duration", [
    ("framepack", "t2v", 5), ("ltx", "t2v", 5), ("ltx", "i2v", 10), ("combinado", "t2v", 10),
])
def test_modes_end_to_end(cfg, image, mode, variant, duration):
    ctx, events = make_ctx(cfg)
    req = GenerationRequest(mode=mode, prompt="teste", duration_s=duration, ltx_variant=variant,
                            start_image=image, seed=7)
    entry = run_generation(ctx, req)
    info = vu.probe(Path(entry.video_path))
    assert (info["width"], info["height"]) == (216, 384)
    assert abs(info["duration"] - duration) < 1.0
    assert info["has_audio"] == (mode != "framepack")
    assert events[-1][0] == 1.0
    assert Path(entry.thumbnail_path).exists()
    assert len(ctx.storage.load_history()) == 1
    assert not any((cfg.output_dir / "_work").iterdir())


def test_stop_motion_post_fps(cfg, image):
    ctx, _ = make_ctx(cfg)
    entry = run_generation(ctx, GenerationRequest(mode="framepack", prompt="", preset="Stop-motion style",
                                                  duration_s=5, start_image=image))
    assert round(vu.probe(Path(entry.video_path))["fps"]) == 12


def test_framepack_requires_image(cfg):
    ctx, _ = make_ctx(cfg)
    with pytest.raises(UserFacingError, match="imagem inicial"):
        run_generation(ctx, GenerationRequest(mode="framepack", prompt="x"))


class FlakyVramBackend(DemoBackend):
    """Falha por falta de VRAM enquanto a resolução for maior que 400px."""

    def __init__(self):
        super().__init__(step_delay=0)
        self.widths = []

    def generate(self, kind, params, work_dir, on_progress):
        self.widths.append(params.width)
        if params.width > 400:
            raise ComfyOOMError("VRAM insuficiente")
        return super().generate(kind, params, work_dir, on_progress)


def test_oom_lowers_quality_and_retries(cfg, image):
    backend = FlakyVramBackend()
    ctx, events = make_ctx(cfg, backend, profile="alto")
    entry = run_generation(ctx, GenerationRequest(mode="framepack", prompt="x", start_image=image))
    assert backend.widths == [544, 480, 384]
    assert entry.profile == "baixo"
    assert any("reduzindo qualidade" in m for _, m in events)


def test_job_queue_runs_in_order(cfg, image):
    manager = JobManager(DemoBackend(step_delay=0.05), Storage(cfg.output_dir), cfg)
    req = GenerationRequest(mode="framepack", prompt="x", start_image=image)
    jobs = [manager.submit(req, PROFILE_BY_KEY["baixo"]) for _ in range(3)]
    manager.cancel(jobs[2].id)
    deadline = time.time() + 60
    while not all(j.finished for j in jobs) and time.time() < deadline:
        time.sleep(0.1)
    assert [j.status for j in jobs] == [JobStatus.DONE, JobStatus.DONE, JobStatus.CANCELLED]


def test_job_failure_is_friendly(cfg):
    manager = JobManager(DemoBackend(step_delay=0), Storage(cfg.output_dir), cfg)
    job = manager.submit(GenerationRequest(mode="combinado", prompt="x"), PROFILE_BY_KEY["baixo"])
    while not job.finished:
        time.sleep(0.05)
    assert job.status == JobStatus.FAILED and "imagem inicial" in job.error
