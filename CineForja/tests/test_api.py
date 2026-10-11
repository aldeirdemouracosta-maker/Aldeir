import time

import pytest
from fastapi.testclient import TestClient

from cineforja.api import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CINEFORJA_OUTPUT_DIR", str(tmp_path / "proj"))
    with TestClient(create_app(str(tmp_path / "api.db"))) as c:
        yield c


def settle(c, pid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        d = c.get(f"/projects/{pid}").json()
        if d["status"] != "running":
            return d
        time.sleep(0.05)
    raise AssertionError("timeout")


def start(c, pid="p1"):
    r = c.post("/projects", json={"brief": "robô dança", "project_id": pid})
    assert r.status_code == 202
    return settle(c, pid)


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "CineForja" in r.text


def test_full_flow_through_api(client):
    d = start(client)
    assert (d["status"], d["waiting_for"]) == ("paused", "asset_designer")
    assert len(d["storyboard"]) == 3
    seen = [d["waiting_for"]]
    while d["status"] == "paused":
        assert client.post("/projects/p1/continue").status_code == 202
        d = settle(client, "p1")
        seen.append(d["waiting_for"])
    assert seen == ["asset_designer", "audio_designer", "editor", None]
    assert d["status"] == "done" and d["output_path"].endswith("final.mp4")
    assert client.get("/projects").json() == ["p1"]


def test_edit_storyboard_only_at_approval(client):
    start(client)
    r = client.put("/projects/p1/storyboard", json={"shots": [{"prompt": "só um shot"}]})
    assert r.status_code == 200 and [s["prompt"] for s in r.json()["storyboard"]] == ["só um shot"]
    client.post("/projects/p1/continue"); d = settle(client, "p1")
    assert len(d["storyboard"]) == 1 and d["waiting_for"] == "audio_designer"
    assert client.put("/projects/p1/storyboard", json={"shots": [{"prompt": "x"}]}).status_code == 409


def test_selective_regeneration(client):
    start(client)
    client.post("/projects/p1/continue"); d = settle(client, "p1")
    assert d["waiting_for"] == "audio_designer"
    before = {s["index"]: s["attempts"] for s in d["storyboard"]}
    r = client.post("/projects/p1/regenerate", json={"shots": [2], "prompts": {"2": "novo prompt"}})
    assert r.status_code == 202
    d = settle(client, "p1")
    after = {s["index"]: s for s in d["storyboard"]}
    assert d["waiting_for"] == "audio_designer"             # voltou à revisão de frames
    assert after[2]["prompt"] == "novo prompt" and after[2]["attempts"] == 1 and after[2]["status"] == "done"
    assert {i: after[i]["attempts"] for i in (0, 1)} == {i: before[i] for i in (0, 1)}  # os outros intactos


def test_regenerate_validation(client):
    start(client)
    assert client.post("/projects/p1/regenerate", json={"shots": [0]}).status_code == 409  # fora da revisão
    client.post("/projects/p1/continue"); settle(client, "p1")
    assert client.post("/projects/p1/regenerate", json={"shots": [99]}).status_code == 400


def test_validation_and_errors(client):
    assert client.post("/projects", json={"brief": ""}).status_code == 422
    assert client.post("/projects", json={"brief": "x", "project_id": "../x"}).status_code == 400
    assert client.get("/projects/nao-existe").status_code == 404
    assert client.get("/projects/..%2Fx").status_code in (400, 404)
    start(client)
    assert client.post("/projects", json={"brief": "x", "project_id": "p1"}).status_code == 409


def test_media_is_confined_to_output_dir(client, tmp_path):
    import os

    from cineforja.orchestrator.hitl import config_for
    start(client)
    assert client.get("/projects/p1/shots/0/media").status_code == 404   # sem arquivo real
    assert client.get("/projects/p1/final").status_code == 404

    proj = tmp_path / "proj"; proj.mkdir(exist_ok=True)
    inside = proj / "ok.png"; inside.write_bytes(b"IMG")
    outside = tmp_path / "segredo.txt"; outside.write_text("segredo")
    link = proj / "link.png"; os.symlink(outside, link)                   # symlink aponta para fora

    def set_path(path):
        board = client.app.state.graph.get_state(config_for("p1")).values["storyboard"]
        board[0].update(status="done", frames_path=str(path))
        client.app.state.graph.update_state(config_for("p1"), {"storyboard": board})
        return client.get("/projects/p1/shots/0/media")

    r = set_path(inside)
    assert r.status_code == 200 and r.content == b"IMG"
    assert set_path(outside).status_code == 404
    assert set_path(link).status_code == 404
    assert set_path("/etc/passwd").status_code == 404


def test_state_survives_api_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("CINEFORJA_OUTPUT_DIR", str(tmp_path / "proj"))
    db = str(tmp_path / "r.db")
    with TestClient(create_app(db)) as c:
        start(c, "rr")
    with TestClient(create_app(db)) as c2:                      # "reinício" do servidor
        d = c2.get("/projects/rr").json()
        assert (d["status"], d["waiting_for"]) == ("paused", "asset_designer")
        c2.post("/projects/rr/continue"); assert settle(c2, "rr")["waiting_for"] == "audio_designer"


def test_get_right_after_start_is_running_not_404(tmp_path, monkeypatch):
    import time as _t

    from cineforja.orchestrator import graph as g
    real = g.director
    monkeypatch.setattr(g, "director", lambda s: (_t.sleep(0.4), real(s))[1])  # atrasa o 1º checkpoint
    monkeypatch.setenv("CINEFORJA_OUTPUT_DIR", str(tmp_path / "proj"))
    with TestClient(create_app(str(tmp_path / "s.db"))) as c:
        c.post("/projects", json={"brief": "x", "project_id": "slow"})
        r = c.get("/projects/slow")
        assert r.status_code == 200 and r.json()["status"] == "running"
        assert "slow" in c.get("/projects").json()
        assert settle(c, "slow")["waiting_for"] == "asset_designer"
