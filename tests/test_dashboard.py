import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.resources import ResourceMonitor
from app.dashboard import STATIC_DIR
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent


class P:
    name = "p"
    async def generate(self, m, p, system=None): return "r"
    async def list_models(self): return ["qwen2.5:0.5b"]
    async def loaded_models(self): return []


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(state_path=tmp_path / "s.db"), provider=P(),
                                 monitor=ResourceMonitor(gpu_query=lambda: "")))


NAV = {"sec-fetch-site": "none", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document",
       "accept": "text/html"}


@pytest.mark.parametrize("path", ["/", "/dashboard"])
def test_direct_browser_navigation_is_allowed(client, path):
    """Regressão do antigo HTTP 403 ao abrir / e /dashboard direto no navegador."""
    for headers in (NAV, {**NAV, "sec-fetch-site": "cross-site"}, {}, {"host": "localhost:8000"}):
        r = client.get(path, headers=headers)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "SWARM LITE AI" in r.text


def test_assets_served_with_correct_types_and_security_headers(client):
    for name, ctype in (("app.js", "javascript"), ("lib.js", "javascript"), ("style.css", "text/css")):
        r = client.get(f"/static/{name}", headers={"sec-fetch-site": "same-origin"})
        assert r.status_code == 200 and ctype in r.headers["content-type"]
    r = client.get("/dashboard")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/resources").headers["cache-control"] == "no-store"


def test_cross_origin_reads_of_data_are_blocked(client):
    evil = {"origin": "http://evil.example", "sec-fetch-site": "cross-site"}
    for path in ("/resources", "/scheduler", "/management/agents", "/management/models", "/agents", "/static/app.js"):
        assert client.get(path, headers=evil).status_code == 403, path
        assert client.get(path, headers={"sec-fetch-site": "cross-site"}).status_code == 403, path
    assert client.get("/resources", headers={"sec-fetch-site": "same-origin"}).status_code == 200


def test_dns_rebinding_host_is_rejected_even_for_dashboard(client):
    for path in ("/", "/dashboard", "/resources"):
        assert client.get(path, headers={"host": "attacker.example"}).status_code == 400


def test_static_does_not_traverse_or_expose_source(client):
    for p in ("/static/../main.py", "/static/%2e%2e/main.py", "/static/..%2fconfig.py", "/static/nao-existe.js"):
        r = client.get(p)
        assert r.status_code in (400, 404) and "create_app" not in r.text
    assert client.post("/dashboard").status_code == 405     # somente leitura


def test_dashboard_data_endpoints_have_expected_shape(client):
    """O JS depende destes campos; se mudarem, este teste avisa."""
    a = client.get("/management/agents").json()[0]
    assert {"name", "enabled", "model", "actions", "available", "reason"} <= set(a)
    assert {"installed", "loaded"} <= set(client.get("/management/models").json())
    r = client.get("/resources").json()
    assert {"cpu_percent", "cpu_count", "ram_total_mb", "ram_used_mb", "ram_available_mb", "gpus"} <= set(r)
    s = client.get("/scheduler").json()
    assert {"running", "queued", "max_concurrent", "max_queue", "timeout", "memory", "jobs", "recent"} <= set(s)
    assert {"reserved_mb", "headroom_mb"} <= set(s["memory"])
    assert client.get("/health").json()["status"] == "ok"


def test_dashboard_is_minimal():
    total = sum(f.stat().st_size for f in STATIC_DIR.iterdir())
    assert total < 16_000, total        # referência de minimalismo (original ~11 KB), não limite rígido


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_javascript_suite_passes():
    r = subprocess.run(["node", "--test", "tests/js/lib.test.cjs"], cwd=ROOT, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
