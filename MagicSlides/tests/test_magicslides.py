import base64
import io
import json
import sys
import threading
import urllib.error
import urllib.request
import zipfile

import pytest
from PIL import Image

from magicslides import ai, config, imagegen, images, layouts, server
from magicslides.core import default_presentation, normalize_presentation, validate_presentation
from magicslides.html_export import build_html
from magicslides.pptx_export import build_pptx


def _png_bytes(w=64, h=40, color=(200, 80, 40)):
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "PNG")
    return out.getvalue()


def _data_url(w=64, h=40):
    return "data:image/png;base64," + base64.b64encode(_png_bytes(w, h)).decode()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGICSLIDES_HOME", str(tmp_path))
    for env in config.ENV_FALLBACK.values():
        monkeypatch.delenv(env, raising=False)


# ------------------------------------------------------------------- core ---

def test_default_presentation_is_valid():
    p = default_presentation()
    assert p["schema"] == "magicslides.presentation"
    assert validate_presentation(p) == []


def test_legacy_gamma_livre_project_is_migrated():
    legacy = {"schema": "gamma-livre.presentation", "version": "0.1.0", "meta": {"title": "Antigo"},
              "theme": {"background": "#F7F7FA", "foreground": "#16181D", "accent": "#6657FF"},
              "slides": [{"id": "s1", "elements": [{"id": "t1", "type": "text", "x": 1, "y": 1, "w": 10, "h": 5, "text": "oi"}]}]}
    data = normalize_presentation(legacy)
    assert data["schema"] == "magicslides.presentation"
    assert validate_presentation(data) == []


def test_validation_rejects_remote_image_src_and_duplicates():
    p = default_presentation()
    el = p["slides"][0]["elements"][0]
    p["slides"][0]["elements"].append(dict(el))
    p["slides"][0]["elements"].append({"id": "img", "type": "image", "x": 0, "y": 0, "w": 10, "h": 10, "src": "http://x/y.png"})
    errors = validate_presentation(p)
    assert any("duplicado" in e for e in errors)
    assert any("data URL" in e for e in errors)


# ---------------------------------------------------------------- layouts ---

def test_every_layout_builds_valid_slides():
    specs = [{"layout": name, "title": f"Título {name}", "bullets": ["Um", "Dois", "Três"], "body": "Texto",
              "quote": "Uma frase", "quote_author": "Alguém", "image_query": "solar panels",
              "stats": [{"value": "73%", "label": "algo"}], "columns": [{"heading": "A", "bullets": ["x"]}, {"heading": "B", "bullets": ["y"]}]}
             for name in layouts.LAYOUTS]
    outline = layouts.normalize_outline({"title": "Teste", "slides": specs})
    pres = layouts.build_presentation(outline, "minimal")
    assert validate_presentation(pres) == []
    assert len(pres["slides"]) == len(layouts.LAYOUTS)
    kinds = {e["type"] for s in pres["slides"] for e in s["elements"]}
    assert kinds == {"text", "shape", "image"}


def test_normalize_outline_is_defensive():
    outline = layouts.normalize_outline({"slides": [{"layout": "???", "bullets": "a\nb", "stats": "x"}, 5, None]})
    assert outline["slides"][0]["layout"] == "title"
    assert outline["slides"][1]["layout"] == "bullets"
    assert outline["slides"][1]["bullets"] == ["a", "b"]


def test_fit_font_shrinks_long_text():
    short = layouts.fit_font("Oi", 40, 10, 40)
    long = layouts.fit_font("palavra " * 120, 40, 10, 40)
    assert short == 40 and long < 20


# --------------------------------------------------------------------- IA ---

def test_offline_skeleton_for_short_topic():
    outline, used = ai.generate_outline("Energia solar", 8, "pt", "", {"provider": "offline"})
    assert "offline" in used.lower()
    assert len(outline["slides"]) == 8
    assert outline["slides"][0]["layout"] == "title"
    assert outline["slides"][-1]["layout"] == "closing"


def test_offline_structures_pasted_text():
    text = "Minha palestra\n# Introdução\n- ponto um\n- ponto dois\n# Conclusão\nFrase um. Frase dois."
    outline, _ = ai.generate_outline(text, 10, "pt", "", {"provider": "offline"})
    titles = [s["title"] for s in outline["slides"]]
    assert titles[0] == "Minha palestra"
    assert "Introdução" in titles and "Conclusão" in titles
    intro = outline["slides"][titles.index("Introdução")]
    assert intro["bullets"] == ["ponto um", "ponto dois"]


def test_parse_json_object_handles_fences_and_noise():
    assert ai.parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.parse_json_object('Aqui está: {"a": 2} fim') == {"a": 2}
    with pytest.raises(ai.AIError):
        ai.parse_json_object("sem json")


def test_outline_schema_is_strict():
    def check(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])
    check(ai.OUTLINE_SCHEMA)


def test_openai_compatible_provider(monkeypatch):
    captured = {}

    class FakeResp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        content = json.dumps({"title": "T", "subtitle": "", "slides": [{"layout": "bullets", "title": "A", "bullets": ["x"]}]})
        return FakeResp(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    cfg = {"provider": "openai", "openai_base_url": "http://localhost:11434/v1/", "openai_model": "llama3.1"}
    outline, used = ai.generate_outline("tema", 5, "pt", "", cfg)
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["body"]["model"] == "llama3.1"
    assert outline["slides"][1]["title"] == "A"
    assert "llama3.1" in used


def test_anthropic_provider_builds_structured_request(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    calls = {}

    class Block:
        type = "text"
        text = json.dumps({"title": "IA", "subtitle": "", "slides": [{"layout": "title", "title": "IA"}]})

    class Msg:
        stop_reason = "end_turn"
        content = [Block()]

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return Msg()

    class FakeBetaMessages:
        def stream(self, **kw):
            calls.update(kw)
            return Stream()

    class FakeClient:
        def __init__(self, api_key=None):
            calls["api_key"] = api_key
            self.beta = type("B", (), {"messages": FakeBetaMessages()})()
            self.messages = FakeBetaMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    cfg = {"provider": "anthropic", "anthropic_api_key": "sk-test", "anthropic_model": "claude-opus-5", "anthropic_effort": "medium"}
    outline, _ = ai.generate_outline("tema", 4, "pt", "", cfg)
    assert outline["title"] == "IA"
    assert calls["api_key"] == "sk-test"
    assert calls["model"] == "claude-opus-5"
    assert calls["fallbacks"] == "default"
    assert calls["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in calls


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI só existe no Windows")
def test_api_keys_are_encrypted_on_disk_on_windows():
    config.save({"anthropic_api_key": "sk-ant-segredo123"})
    assert "sk-ant-segredo123" not in config.config_path().read_text(encoding="utf-8")
    assert config.load()["anthropic_api_key"] == "sk-ant-segredo123"


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI só existe no Windows")
def test_dpapi_failure_keeps_key_and_warns(monkeypatch, capsys):
    def broken(data, protect):
        raise OSError("sem DPAPI")

    monkeypatch.setattr(config, "_dpapi", broken)
    config.save({"anthropic_api_key": "sk-sem-cofre"})
    assert config.load()["anthropic_api_key"] == "sk-sem-cofre"
    assert "sem criptografia" in capsys.readouterr().err


def test_old_plaintext_config_still_loads():
    config.config_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_path().write_text(json.dumps({"anthropic_api_key": "sk-antigo"}), encoding="utf-8")
    assert config.load()["anthropic_api_key"] == "sk-antigo"


def test_offline_image_query_has_no_repeated_words():
    text = "Energia Solar\nEnergia Solar Direta\n- Painel solar\n- Uso em casas\nEnergia Solar Indireta\n- Água quente\n- Calor"
    outline, _ = ai.generate_outline(text, 6, "pt", "", {"provider": "offline"})
    queries = [s.get("image_query", "") for s in outline["slides"] if s["layout"].startswith("image")]
    assert queries and all(len(q.split()) == len({w.lower() for w in q.split()}) for q in queries), queries
    assert any("Direta" in q or "Indireta" in q for q in queries), queries


def test_prompt_asks_for_substantive_content_and_adapts_to_input_size():
    short = ai.build_user_prompt("Energia solar", 8, "Português do Brasil", "")
    long_ = ai.build_user_prompt("Energia solar. " * 60, 8, "Português do Brasil", "")
    assert "only a short topic" in short and "text/outline" not in short
    assert "text/outline" in long_ and "only a short topic" not in long_
    assert "SUBSTANTIVE" in ai.SYSTEM_PROMPT and "Never repeat the same idea" in ai.SYSTEM_PROMPT


def test_anthropic_effort_only_for_models_that_support_it(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    seen = []

    class Block:
        type = "text"
        text = json.dumps({"title": "IA", "subtitle": "", "slides": [{"layout": "title", "title": "IA"}]})

    class Msg:
        stop_reason = "end_turn"
        content = [Block()]

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return Msg()

    class FakeMessages:
        def stream(self, **kw):
            seen.append(kw)
            return Stream()

    class FakeClient:
        def __init__(self, api_key=None):
            self.beta = type("B", (), {"messages": FakeMessages()})()
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    for model in ("claude-haiku-4-5", "claude-opus-5-5"):
        ai.generate_outline("tema", 4, "pt", "", {"provider": "anthropic", "anthropic_model": model,
                                                  "anthropic_api_key": "k", "anthropic_effort": "medium"})
    assert "effort" not in seen[0]["output_config"]
    assert seen[1]["output_config"]["effort"] == "medium"


def test_anthropic_retries_without_effort_when_model_rejects_it(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx2", reason="SDK anthropic usa httpx2")
    calls = []

    class Block:
        type = "text"
        text = json.dumps({"title": "IA", "subtitle": "", "slides": [{"layout": "title", "title": "IA"}]})

    class Msg:
        stop_reason = "end_turn"
        content = [Block()]

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return Msg()

    class FakeMessages:
        def stream(self, **kw):
            calls.append(dict(kw, output_config=dict(kw["output_config"])))
            if "effort" in kw["output_config"]:
                response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
                raise anthropic.BadRequestError("unsupported parameter: output_config.effort",
                                                response=response, body=None)
            return Stream()

    class FakeClient:
        def __init__(self, api_key=None):
            self.beta = type("B", (), {"messages": FakeMessages()})()
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    cfg = {"provider": "anthropic", "anthropic_api_key": "k", "anthropic_model": "claude-sonnet-4-0",
           "anthropic_effort": "medium"}
    outline, _ = ai.generate_outline("tema", 4, "pt", "", cfg)
    assert outline["title"] == "IA"
    assert len(calls) == 2
    assert "effort" in calls[0]["output_config"] and "effort" not in calls[1]["output_config"]


# ---------------------------------------------------------------- imagens ---

def test_fill_images_uses_results_and_placeholders(monkeypatch):
    def fake_source(query, per_page, cfg):
        if "nada" in query:
            return []
        return [{"id": f"x:{query}", "source": "openverse", "title": query, "thumb": "", "url": f"https://img.example/{query}.png",
                 "width": 800, "height": 500, "author": "Fulano", "license": "CC BY 4.0", "page": "https://example.org"}]

    monkeypatch.setitem(images.SOURCES, "openverse", fake_source)
    monkeypatch.setattr(images, "download_data_url", lambda url, max_side=1600: (_data_url(), 64, 40))
    outline = layouts.normalize_outline({"title": "T", "slides": [
        {"layout": "title", "title": "T"},
        {"layout": "image-right", "title": "A", "image_query": "sol"},
        {"layout": "image-left", "title": "B", "image_query": "nada"},
    ]})
    pres = layouts.build_presentation(outline, "aurora")
    credits, warnings = images.fill_presentation_images(pres, {"image_sources": ["openverse"]})
    assert len(credits) == 1 and "Fulano" in credits[0]
    imgs = [e for s in pres["slides"] for e in s["elements"] if e["type"] == "image"]
    assert len(imgs) == 1 and imgs[0]["src"].startswith("data:image/")
    placeholders = [e for s in pres["slides"] for e in s["elements"] if "placeholderQuery" in e]
    assert placeholders and placeholders[0]["placeholderQuery"] == "nada"
    assert validate_presentation(pres) == []


def test_ssrf_guard_blocks_local_addresses():
    for url in ("http://127.0.0.1/x.png", "http://localhost/x.png", "file:///etc/passwd", "http://10.0.0.1/a.jpg"):
        with pytest.raises(images.ImageError):
            images._check_public_url(url)


def test_redirect_to_private_address_is_blocked():
    handler = images._SafeRedirect()
    req = urllib.request.Request("https://example.org/a.png")
    with pytest.raises(images.ImageError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/secret")


def test_encode_image_downscales_and_converts():
    raw = _png_bytes(3000, 1500)
    data_url, w, h = images.encode_image(raw, 1600)
    assert data_url.startswith("data:image/jpeg;base64,")
    assert (w, h) == (1600, 800)


def test_configured_sources_prefer_keyed_sources():
    cfg = {"image_sources": ["openverse"], "pexels_api_key": "k"}
    assert images.configured_sources(cfg) == ["pexels", "openverse"]
    assert images.configured_sources({"image_sources": ["pexels"]}) == []


# ----------------------------------------------------------- configuração ---

def test_settings_never_expose_keys():
    config.save({"provider": "anthropic", "anthropic_api_key": "sk-secret"})
    view = config.public_view()
    assert view["has_anthropic_api_key"] is True
    assert "sk-secret" not in json.dumps(view)
    config.save({"anthropic_api_key": ""})  # vazio mantém a chave
    assert config.load()["anthropic_api_key"] == "sk-secret"
    config.save({"anthropic_api_key": "__clear__"})
    assert config.load()["anthropic_api_key"] == ""


# ------------------------------------------------------------- exportação ---

def _rich_presentation():
    outline = layouts.normalize_outline({"title": "Export", "slides": [
        {"layout": "title", "title": "Export", "subtitle": "sub"},
        {"layout": "image-right", "title": "Com imagem", "bullets": ["a", "b"], "image_query": "q", "notes": "fale isso"},
        {"layout": "stats", "title": "Números", "stats": [{"value": "10%", "label": "x"}]},
        {"layout": "image-full", "title": "Full", "body": "texto", "image_query": "q2"},
    ]})
    pres = layouts.build_presentation(outline, "terracota")
    for s in pres["slides"]:
        for e in s["elements"]:
            if e["type"] == "image":
                e["src"] = _data_url(300, 100)
                e["credit"] = "Foto por Fulano"
    return pres


def test_pptx_export_contains_slides_notes_bullets_and_crop():
    from pptx import Presentation

    blob = build_pptx(_rich_presentation())
    assert blob[:2] == b"PK"
    prs = Presentation(io.BytesIO(blob))
    assert len(prs.slides) == 4
    assert prs.slide_width == 12192000
    s2 = prs.slides[1]
    assert "fale isso" in s2.notes_slide.notes_text_frame.text
    assert "Fulano" in s2.notes_slide.notes_text_frame.text
    pics = [sh for sh in s2.shapes if sh.shape_type == 13]
    assert pics and (pics[0].crop_left > 0 or pics[0].crop_top > 0)
    xml = zipfile.ZipFile(io.BytesIO(blob)).read("ppt/slides/slide2.xml").decode()
    assert "buChar" in xml
    xml4 = zipfile.ZipFile(io.BytesIO(blob)).read("ppt/slides/slide4.xml").decode()
    assert "<a:alpha" in xml4


def test_html_export_is_self_contained_and_escaped():
    pres = _rich_presentation()
    pres["slides"][0]["elements"][2]["text"] = "<script>alert(1)</script>"
    html = build_html(pres).decode()
    assert html.count('class="slide"') == 4
    assert "<script>alert(1)</script>" not in html
    assert "data:image/png;base64" in html


def test_html_export_rejects_malformed_colors():
    pres = _rich_presentation()
    pres["slides"][0]["elements"][2]["color"] = '#"onx=1'
    html = build_html(pres).decode()
    assert 'onx=1' not in html


def test_html_export_sanitizes_align_and_font_and_ignores_nan():
    pres = _rich_presentation()
    text = next(e for s in pres["slides"] for e in s["elements"] if e["type"] == "text")
    text["align"] = "left;background:url(https://evil.example/x)"
    text["font"] = "Arial';background:url(https://evil.example/x)"
    shape = next(e for s in pres["slides"] for e in s["elements"] if e["type"] == "shape")
    shape["opacity"] = float("nan")
    html = build_html(pres).decode()
    assert "url(" not in html and "https://" not in html
    assert "text-align:left;justify-content:" in html
    assert "font-family:'Arialbackgroundurlhttpsevil.examplex'" in html
    assert "opacity:1.000" in html and "opacity:nan" not in html


# ----------------------------------------------------------------- servidor ---

@pytest.fixture()
def live_server():
    httpd = server.make_server("127.0.0.1", 0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _req(url, body=None, token=True, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["X-MagicSlides-Token"] = server.TOKEN
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=30)


def test_server_requires_token_and_injects_it(live_server):
    page = urllib.request.urlopen(live_server + "/").read().decode()
    assert server.TOKEN in page and "__MS_TOKEN__" not in page
    with pytest.raises(urllib.error.HTTPError) as err:
        _req(live_server + "/api/export/pptx", default_presentation(), token=False)
    assert err.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as err:
        _req(live_server + "/api/settings", token=True, headers={"Host": "evil.example"})
    assert err.value.code == 403


def test_server_rejects_non_object_json(live_server):
    with pytest.raises(urllib.error.HTTPError) as err:
        _req(live_server + "/api/settings", [1, 2, 3])
    assert err.value.code == 400


def test_server_blocks_path_traversal(live_server):
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(live_server + "/../server.py")
    assert err.value.code == 404


def test_server_generation_job_offline_without_images(live_server):
    import time

    job = json.load(_req(live_server + "/api/generate", {"prompt": "Reciclagem", "slides": 6, "images": False, "theme": "floresta"}))["job"]
    for _ in range(100):
        st = json.load(_req(f"{live_server}/api/jobs/{job}"))
        if st["state"] != "running":
            break
        time.sleep(0.05)
    assert st["state"] == "done", st
    pres = st["result"]
    assert len(pres["slides"]) == 6
    assert pres["theme"]["id"] == "floresta"
    assert validate_presentation(pres) == []
    assert not any(e["type"] == "image" for s in pres["slides"] for e in s["elements"])
    blob = _req(live_server + "/api/export/pptx", pres).read()
    assert blob[:2] == b"PK"


def test_server_validate_returns_migrated_presentation(live_server):
    legacy = default_presentation()
    legacy["schema"] = "gamma-livre.presentation"
    res = json.load(_req(live_server + "/api/validate", legacy))
    assert res["presentation"]["schema"] == "magicslides.presentation"


def test_server_encode_endpoint(live_server):
    res = json.load(_req(live_server + "/api/images/encode", {"dataUrl": _data_url(50, 50)}))
    assert res["src"].startswith("data:image/")


# ----------------------------------------------------------------- desktop ---

def test_desktop_api_exposes_only_methods():
    """pywebview percorre atributos públicos do js_api; um objeto Window
    público ali trava a janela no Windows (regressão)."""
    import inspect

    from magicslides.desktop import DesktopApi

    api = DesktopApi()
    api.attach(object())
    public = {n: getattr(api, n) for n in dir(api) if not n.startswith("_")}
    assert public, "deveria expor save_file"
    for name, attr in public.items():
        assert inspect.ismethod(attr), f"atributo público não-método: {name}"



# ------------------------------------------- imagens geradas por IA / texto ---

def _ig_png(color=(200, 40, 40), size=(64, 36)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class _FakeResp:
    def __init__(self, payload: bytes):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._p if n < 0 else self._p[:n]


def test_imagegen_gemini_parses_inline_data(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"], seen["key"] = req.full_url, req.headers.get("X-goog-api-key")
        body = {"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {
            "mimeType": "image/png", "data": base64.b64encode(_ig_png()).decode()}}]}}]}
        return _FakeResp(json.dumps(body).encode())

    monkeypatch.setattr(imagegen.urllib.request, "urlopen", fake_urlopen)
    cfg = {"imagegen_provider": "gemini", "imagegen_api_key": "k", "imagegen_model": "gemini-x-image"}
    src, w, h = imagegen.generate("painéis solares", cfg)
    assert src.startswith("data:image/") and (w, h) == (64, 36)
    assert "gemini-x-image:generateContent" in seen["url"] and seen["key"] == "k"


def test_imagegen_gemini_requires_key_and_reports_no_image(monkeypatch):
    with pytest.raises(images.ImageError, match="chave"):
        imagegen.generate("x", {"imagegen_provider": "gemini"})
    monkeypatch.setattr(imagegen.urllib.request, "urlopen",
                        lambda req, timeout=0: _FakeResp(b'{"candidates": [{"content": {"parts": [{"text": "so texto"}]}}]}'))
    with pytest.raises(images.ImageError, match="não devolveu imagem"):
        imagegen.generate("x", {"imagegen_provider": "gemini", "imagegen_api_key": "k"})


def test_imagegen_openai_compatible_b64_and_size(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data)
        return _FakeResp(json.dumps({"data": [{"b64_json": base64.b64encode(_ig_png((10, 90, 200))).decode()}]}).encode())

    monkeypatch.setattr(imagegen.urllib.request, "urlopen", fake_urlopen)
    cfg = {"imagegen_provider": "openai", "imagegen_base_url": "https://api.example.com/v1/", "imagegen_model": "gpt-image-1",
           "imagegen_api_key": "k"}
    src, _, _ = imagegen.generate("cidade à noite", cfg)
    assert src.startswith("data:image/")
    assert seen["url"] == "https://api.example.com/v1/images/generations"
    assert seen["body"]["model"] == "gpt-image-1" and seen["body"]["size"] == "1536x1024"


def test_imagegen_pollinations_needs_no_key(monkeypatch):
    seen = {}
    monkeypatch.setattr(imagegen.urllib.request, "urlopen",
                        lambda req, timeout=0: (seen.setdefault("url", req.full_url), _FakeResp(_ig_png()))[1])
    src, _, _ = imagegen.generate("solar panels", {"imagegen_provider": "pollinations"})
    assert src.startswith("data:image/") and seen["url"].startswith("https://image.pollinations.ai/prompt/")


def test_fill_images_in_ai_mode_credits_once_and_placeholders_on_failure(monkeypatch):
    calls = []

    def fake_generate(prompt, cfg):
        calls.append(prompt)
        if "falha" in prompt:
            raise images.ImageError("Gemini: limite de uso atingido.")
        return _data_url(), 64, 40

    monkeypatch.setattr(imagegen, "generate", fake_generate)
    outline, _ = ai.generate_outline("Energia solar", 4, "pt", "", {"provider": "offline"})
    pres = layouts.build_presentation(outline, None)
    for s in pres["slides"]:
        for e in s["elements"]:
            if e["type"] == "image" and s["name"] == "Por que isso importa":
                e["query"] = "falha total"
    credits, warnings = images.fill_presentation_images(pres, {"imagegen_provider": "gemini"}, mode="ai")
    assert calls and all("No text" in c for c in calls)
    filled = [e for s in pres["slides"] for e in s["elements"] if e["type"] == "image" and e["src"]]
    assert filled and all(e["source"] == "ai" and "gerada por IA" in e["credit"] for e in filled)
    assert len(credits) == 1 and "gerada por IA" in credits[0]


def test_text_scale_changes_font_sizes_and_detail_changes_prompt():
    outline, _ = ai.generate_outline("Energia solar\n- um\n- dois", 5, "pt", "", {"provider": "offline"})
    sizes = {k: max(e["fontSize"] for s in layouts.build_presentation(outline, None, text_scale=k)["slides"]
                    for e in s["elements"] if e["type"] == "text") for k in ("small", "normal", "xlarge")}
    assert sizes["small"] < sizes["normal"] < sizes["xlarge"]
    assert layouts.parse_text_scale("large") > 1 > layouts.parse_text_scale("small")
    assert layouts.parse_text_scale("lixo") == 1.0 and layouts.parse_text_scale(99) == 1.8
    extensive = ai.build_user_prompt("Tema", 6, "pt", "", "extensive")
    basic = ai.build_user_prompt("Tema", 6, "pt", "", "basic")
    assert "EXTENSIVE" in extensive and "BASIC" in basic and extensive != basic
    assert "TEXT AMOUNT: MEDIUM" in ai.build_user_prompt("Tema", 6, "pt", "", "inexistente")
    assert "EXTENSIVE" in ai.build_user_prompt("Tema", 6, "pt", "", "detailed")   # nome antigo ainda vale


def test_generate_endpoint_and_settings_hide_imagegen_key(live_server, monkeypatch):
    monkeypatch.setattr(imagegen, "generate", lambda prompt, cfg: (_data_url(), 64, 40))
    config.save({"imagegen_provider": "pollinations", "imagegen_api_key": "segredo-img"})
    token = server.TOKEN
    req = urllib.request.Request(live_server + "/api/images/generate", data=json.dumps({"prompt": "um farol", "title": "Costa"}).encode(),
                                 headers={"X-MagicSlides-Token": token, "Content-Type": "application/json"}, method="POST")
    out = json.load(urllib.request.urlopen(req))
    assert out["ok"] and out["src"].startswith("data:image/") and "gerada por IA" in out["credit"]
    view = config.public_view()
    assert "imagegen_api_key" not in view and view["has_imagegen_api_key"] is True



# ------------------------------------------- reescrever a quantidade de texto ---

def _items():
    return [
        {"id": "a", "kind": "bullets", "slide_title": "Energia solar", "max_chars": 400,
         "text": "Converte luz do sol em eletricidade\nFunciona mesmo em dias nublados\nO painel dura mais de vinte anos\nExige pouca manutenção"},
        {"id": "b", "kind": "paragraph", "slide_title": "Custos", "max_chars": 300,
         "text": "O investimento inicial é alto. Depois a conta de luz cai bastante. O retorno costuma vir em poucos anos."},
    ]


def test_rewrite_offline_only_shortens():
    out, used = ai.rewrite_texts(_items(), "basic", "pt", {"provider": "offline"})
    assert len(out["a"].split("\n")) == 3 and out["b"] == "O investimento inicial é alto."
    same, _ = ai.rewrite_texts(_items(), "medium", "pt", {"provider": "offline"})
    assert same["a"] == _items()[0]["text"]
    with pytest.raises(ai.AIError, match="ampliar"):
        ai.rewrite_texts(_items(), "extensive", "pt", {"provider": "offline"})


def test_rewrite_with_ai_sends_level_and_maps_ids(monkeypatch):
    seen = {}

    def fake(system, user, cfg):
        seen["system"], seen["user"] = system, user
        return {"items": [{"id": "a", "text": "Explicação longa e completa sobre o painel solar."}, {"id": "zzz", "text": "ignorado?"}]}

    monkeypatch.setattr(ai, "_openai_json", fake)
    out, used = ai.rewrite_texts(_items(), "extensive", "Português do Brasil", {"provider": "openai", "openai_model": "m", "openai_base_url": "http://x/v1"})
    assert "EXTENSIVE" in seen["user"] and "max_chars" in seen["user"] and "same ids" in seen["system"]
    assert out["a"].startswith("Explicação longa") and "b" not in out and used.startswith("m @")
    monkeypatch.setattr(ai, "_openai_json", lambda *a: {"items": []})
    with pytest.raises(ai.AIError):
        ai.rewrite_texts(_items(), "basic", "pt", {"provider": "openai", "openai_model": "m", "openai_base_url": "http://x/v1"})


def test_fit_rewritten_trims_overflow_and_scales_font_by_level():
    long_text = "\n".join(f"Tópico {i} com uma explicação bem longa para encher a caixa de texto do slide" for i in range(12))
    text, fs = layouts.fit_rewritten(long_text, 44, 20, True, 24, "extensive")
    assert layouts.text_height(text, 44, 13, True) <= 20 and 0 < len(text.split("\n")) < 12 and fs <= 24
    _, fs_basic = layouts.fit_rewritten("Curto", 44, 20, True, 20, "basic")
    _, fs_ext = layouts.fit_rewritten("Curto", 44, 20, True, 20, "extensive")
    assert fs_basic > fs_ext == 20
    assert layouts.capacity_chars(44, 30, True) > layouts.capacity_chars(20, 10, True)


def test_rewrite_endpoint(live_server, monkeypatch):
    config.save({"provider": "openai", "openai_model": "m", "openai_base_url": "http://x/v1"})
    monkeypatch.setattr(ai, "_openai_json", lambda system, user, cfg: {"items": [{"id": "t1", "text": "Novo texto\nSegundo tópico"}]})
    body = {"level": "medium", "language": "Português do Brasil", "items": [
        {"id": "t1", "text": "Antigo", "bullets": True, "w": 44, "h": 30, "fontSize": 22, "slide_title": "X"},
        {"id": "ruim"}]}
    req = urllib.request.Request(live_server + "/api/rewrite", data=json.dumps(body).encode(), method="POST",
                                 headers={"X-MagicSlides-Token": server.TOKEN, "Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req))
    assert out["ok"] and out["level"] == "medium" and out["items"][0]["id"] == "t1"
    assert out["items"][0]["text"].startswith("Novo texto") and out["items"][0]["fontSize"] > 0
