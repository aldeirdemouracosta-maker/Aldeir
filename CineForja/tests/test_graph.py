import pytest

from cineforja.orchestrator.graph import build_app
from cineforja.orchestrator.hitl import config_for, current_state, edit_state, pending_checkpoint, resume
from cineforja.orchestrator.state import new_state
from cineforja.workers.router import choose_worker


def test_choose_worker():
    assert choose_worker("video") == "cuda"
    assert choose_worker("llm") == "cuda"
    assert choose_worker("audio") == "vulkan"
    assert choose_worker("upscale") == "vulkan"
    assert choose_worker("export") == "cpu"


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "t.db")


def test_full_flow_with_three_interrupts(db):
    app = build_app(db)
    app.invoke(new_state("p1", "um robô aprende a dançar"), config_for("p1"))
    seen = [pending_checkpoint(app, "p1")]
    while seen[-1]:
        resume(app, "p1")
        seen.append(pending_checkpoint(app, "p1"))
    assert seen == ["asset_designer", "audio_designer", "editor", None]
    st = current_state(app, "p1")
    assert st["output_path"].endswith("final.mp4")
    assert all(s["status"] == "done" for s in st["storyboard"])


def test_low_score_triggers_regeneration(db):
    app = build_app(db, interrupt_before=[])
    st = app.invoke(new_state("p2", "x"), config_for("p2"))
    attempts = {s["index"]: s["attempts"] for s in st["storyboard"]}
    assert attempts == {0: 1, 1: 2, 2: 1}  # shot 1 regenerado uma vez


def test_state_survives_restart(db):
    app = build_app(db)
    app.invoke(new_state("p3", "x"), config_for("p3"))
    del app
    app2 = build_app(db)  # nova conexão = "reinício" da máquina
    assert pending_checkpoint(app2, "p3") == "asset_designer"
    assert len(current_state(app2, "p3")["storyboard"]) == 3


def test_edit_state_at_checkpoint(db):
    app = build_app(db)
    app.invoke(new_state("p4", "x"), config_for("p4"))
    board = current_state(app, "p4")["storyboard"][:2]
    edit_state(app, "p4", {"storyboard": board})
    resume(app, "p4")
    assert len(current_state(app, "p4")["storyboard"]) == 2
