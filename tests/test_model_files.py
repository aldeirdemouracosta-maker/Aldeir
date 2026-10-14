import asyncio
import hashlib

import httpx
import pytest

from app.core.model_files import (Manifest, ModelFileError, install, installed_path, load_manifests, remove)

DATA = b"pesos-falsos" * 1000
SHA = hashlib.sha256(DATA).hexdigest()
URL = "https://huggingface.co/x/y/resolve/main/m.gguf"


def run(c):
    return asyncio.run(c)


def man(**kw):
    base = dict(id="m1", agents=["chat"], size_mb=1, license="MIT", status="wired", url=URL, filename="m.gguf")
    return Manifest(**{**base, **kw})


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok_handler(req):
    return httpx.Response(200, content=DATA, headers={"content-length": str(len(DATA))})


def test_real_manifest_loads_and_is_honest():
    from app.config import Settings
    ms = load_manifests(Settings().models_file)
    assert {"qwen2.5-0.5b-instruct-q5_0", "qwen2.5-coder-0.5b-instruct-q4_k_m", "piper-pt_BR-faber-medium"} <= set(ms)
    assert all(m.sha256 is None for m in ms.values())            # nenhum hash foi inventado
    assert ms["sensevoice-small"].size_mb == 936 and "FunASR" in ms["sensevoice-small"].license
    agents = {a for m in ms.values() for a in m.agents}
    assert {"chat", "coder", "ocr", "retrieval", "speech", "voice", "rag", "planner", "langid"} <= agents


def test_install_requires_sha_and_downloads_nothing_without_it(tmp_path):
    hits = []
    def h(req): hits.append(1); return ok_handler(req)
    with pytest.raises(ModelFileError, match="SHA-256"):
        run(install(man(), tmp_path, client=client(h)))
    with pytest.raises(ModelFileError, match="SHA-256"):
        run(install(man(), tmp_path, sha256="abc", client=client(h)))
    assert hits == []


def test_install_ok_verifies_and_is_idempotent(tmp_path):
    n = []
    def h(req): n.append(1); return ok_handler(req)
    p = run(install(man(), tmp_path, sha256=SHA, client=client(h)))
    assert p.read_bytes() == DATA and p == tmp_path / "m1" / "m.gguf" and not list(tmp_path.rglob("*.part"))
    assert installed_path(man(), tmp_path) == p
    run(install(man(), tmp_path, sha256=SHA, client=client(h)))
    assert len(n) == 1                                            # já instalado e íntegro: não baixa de novo
    assert remove(man(), tmp_path) and installed_path(man(), tmp_path) is None


def test_bad_hash_discards_file(tmp_path):
    with pytest.raises(ModelFileError, match="não confere"):
        run(install(man(), tmp_path, sha256="0" * 64, client=client(ok_handler)))
    assert not list(tmp_path.rglob("m.gguf*"))


def test_resume_uses_range(tmp_path):
    d = tmp_path / "m1"; d.mkdir()
    (d / "m.gguf.part").write_bytes(DATA[:5000])
    seen = {}
    def h(req):
        seen["range"] = req.headers.get("range")
        return httpx.Response(206, content=DATA[5000:], headers={"content-length": str(len(DATA) - 5000)})
    p = run(install(man(), tmp_path, sha256=SHA, client=client(h)))
    assert seen["range"] == "bytes=5000-" and p.read_bytes() == DATA


def test_server_ignoring_range_restarts_cleanly(tmp_path):
    d = tmp_path / "m1"; d.mkdir()
    (d / "m.gguf.part").write_bytes(b"lixo antigo")
    assert run(install(man(), tmp_path, sha256=SHA, client=client(ok_handler))).read_bytes() == DATA


@pytest.mark.parametrize("kw,msg", [
    (dict(url="http://huggingface.co/a/b"), "host"),
    (dict(url="https://evil.example/m.gguf"), "host"),
    (dict(url="https://huggingface.co.evil.example/m.gguf"), "host"),
    (dict(filename="../escape.bin"), "inválido"),
    (dict(filename="a/b.bin"), "inválido"),
    (dict(url=None), "manualmente"),
    (dict(size_mb=2000), "1 GB"),
])
def test_install_rejects_unsafe_manifests(tmp_path, kw, msg):
    with pytest.raises(ModelFileError, match=msg):
        run(install(man(**kw), tmp_path, sha256=SHA, client=client(ok_handler)))


def test_large_download_needs_explicit_authorization(tmp_path):
    big = lambda req: httpx.Response(200, content=b"x", headers={"content-length": str(2 * 2**30)})
    with pytest.raises(ModelFileError, match="1 GB"):
        run(install(man(), tmp_path, sha256=SHA, client=client(big)))


def test_redirect_to_foreign_host_is_refused_and_hf_cdn_allowed(tmp_path):
    def evil(req):
        return httpx.Response(302, headers={"location": "https://evil.example/x"})
    with pytest.raises(ModelFileError, match="redirecionamento"):
        run(install(man(), tmp_path, sha256=SHA, client=client(evil)))

    def cdn(req):
        if req.url.host == "huggingface.co":
            return httpx.Response(302, headers={"location": "https://cdn-lfs.hf.co/abc"})
        return ok_handler(req)
    assert run(install(man(), tmp_path, sha256=SHA, client=client(cdn))).read_bytes() == DATA


def test_http_error_and_remove_stays_inside_models_dir(tmp_path):
    with pytest.raises(ModelFileError, match="404"):
        run(install(man(), tmp_path, sha256=SHA, client=client(lambda r: httpx.Response(404))))
    assert remove(man(id=".."), tmp_path / "sub") is False
