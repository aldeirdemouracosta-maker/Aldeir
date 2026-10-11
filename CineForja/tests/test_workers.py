import json
import threading
import urllib.error
import urllib.request

import pytest

from cineforja.orchestrator.graph import build_app
from cineforja.orchestrator.hitl import config_for
from cineforja.orchestrator.state import new_state
from cineforja.workers.client import WorkerError, dispatch
from cineforja.workers.server import WorkerServer


def post(url, path, body):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


@pytest.fixture
def workers(monkeypatch):
    servers = {k: WorkerServer(k) for k in ("cuda", "vulkan")}
    for s in servers.values():
        threading.Thread(target=s.serve_forever, daemon=True).start()
    monkeypatch.setenv("CINEFORJA_WORKERS", ",".join(f"{k}={s.url}" for k, s in servers.items()))
    yield servers
    for s in servers.values():
        s.shutdown()
        s.server_close()


def test_dispatch_routes_to_correct_worker(workers):
    assert dispatch("video", "x") == "[cuda] x"
    assert dispatch("audio", "y") == "[vulkan] y"
    assert workers["cuda"].slot.loaded == "video"
    assert workers["vulkan"].slot.loaded == "audio"


def test_worker_rejects_foreign_task(workers):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(workers["cuda"].url, "/run", {"task_type": "audio", "what": "x"})
    assert e.value.code == 400


def test_invalid_request(workers):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(workers["cuda"].url, "/run", {"what": "sem task"})
    assert e.value.code == 400


def test_only_one_model_resident(workers):
    for task in ["llm", "video", "llm", "consistency", "video"]:
        dispatch(task, "x")
    cuda = workers["cuda"]
    assert cuda.backend.peak == 1
    assert cuda.slot.history[:4] == [("load", "llm"), ("unload", "llm"), ("load", "video"), ("unload", "video")]


def test_concurrent_requests_never_overlap_models(workers):
    tasks = ["llm", "video", "heavy_image", "consistency"] * 8
    threads = [threading.Thread(target=dispatch, args=(t, "x")) for t in tasks]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert workers["cuda"].backend.peak == 1


def test_unload_endpoint(workers):
    dispatch("video", "x")
    post(workers["cuda"].url, "/unload", {})
    assert workers["cuda"].slot.loaded is None and not workers["cuda"].backend.resident


def test_worker_down_raises(monkeypatch):
    monkeypatch.setenv("CINEFORJA_WORKERS", "cuda=http://127.0.0.1:9")
    with pytest.raises(WorkerError):
        dispatch("video", "x")


def test_graph_through_http_workers(workers, tmp_path):
    app = build_app(str(tmp_path / "w.db"), interrupt_before=[])
    st = app.invoke(new_state("w1", "x"), config_for("w1"))
    assert st["output_path"].endswith("final.mp4")
    assert workers["cuda"].backend.peak == 1 and workers["vulkan"].backend.peak == 1
    assert workers["vulkan"].slot.loaded == "audio"
