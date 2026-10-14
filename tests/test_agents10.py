import json

import pytest

from app.agents.coder import CodeFormatError, CoderAgent, enforce_code_only
from app.agents.langid import LangIdAgent, detect_language
from app.agents.planner import MAX_STEPS, PlanError, PlannerAgent, RunContext, parse_plan_json, validate_plan
from app.config import Settings
from app.core.models import OutputError
from app.main import build_service, create_app
from app.multimodal.documents import DocumentIndex
from tests.helpers import client as make_client
from tests.test_multimodal import PNG, Down, EmbProvider, FakeVision, run
from tests.test_stability import mem


# ---------- LangID (real, sem modelo) ----------
@pytest.mark.parametrize("text,lang", [
    ("O gato dorme no sofá porque não quer ir para a rua com a chuva", "pt"),
    ("The quick brown fox jumps over the lazy dog and it was not happy with that", "en"),
    ("El perro de mi vecino no quiere comer porque está muy cansado", "es"),
    ("Le chat est sur la table et il ne veut pas descendre de là", "fr"),
    ("Der Hund ist nicht im Haus und die Katze schläft auf dem Sofa", "de"),
    ("Il gatto dorme sul divano e non vuole andare in giardino", "it"),
    ("今日はとても良い天気ですね。散歩に行きましょう", "ja"),
    ("今天天气很好，我们一起去公园散步吧", "zh"),
    ("오늘은 날씨가 정말 좋아서 공원에 산책하러 갑니다", "ko"),
    ("Сегодня очень хорошая погода, пойдём гулять", "ru"),
])
def test_langid_detects_languages(text, lang):
    assert detect_language(text)[0] == lang


@pytest.mark.parametrize("text", ["", "   ", "ok", "hello", "12345 !!!", "xyzzy qwerty asdf"])
def test_langid_says_unknown_instead_of_guessing(text):
    assert detect_language(text) == ("und", 0.0)


def test_langid_agent_and_validation():
    assert run(LangIdAgent().run("lang_detect", {"text": "The cat is on the table and it is not happy"})).startswith("en")
    with pytest.raises(ValueError):
        run(LangIdAgent().run("lang_detect", {}))


# ---------- Coder code_only ----------
def test_enforce_code_only():
    assert enforce_code_only("```python\nx = 1\n```") == "x = 1\n"
    assert enforce_code_only("x = 1") == "x = 1\n"
    for bad in ("Aqui está:\n```python\nx=1\n```", "```python\nx=1\n```\nEssa função faz X.",
                "```a\n1\n```\n```b\n2\n```", "```python\nx=1"):
        with pytest.raises(CodeFormatError):
            enforce_code_only(bad)


class Replies:
    name = "r"
    def __init__(self, *replies): self.replies, self.calls = list(replies), []
    async def generate(self, model, prompt, system=None):
        self.calls.append(system)
        return self.replies.pop(0)
    async def list_models(self): return ["m"]


def test_coder_code_only_retries_once_then_fails():
    p = Replies("Claro! ```py\nx=1\n```", "```py\nx = 1\n```")
    assert run(CoderAgent(p, "m").run("code_generate", {"text": "x", "output_mode": "code_only"})) == "x = 1\n"
    assert len(p.calls) == 2 and "SOMENTE com o código" in p.calls[1]
    p2 = Replies("texto ```a```", "mais texto ```b```")
    with pytest.raises(OutputError):
        run(CoderAgent(p2, "m").run("code_generate", {"text": "x", "output_mode": "code_only"}))
    with pytest.raises(ValueError):
        run(CoderAgent(p, "m").run("code_review", {"text": "x", "output_mode": "code_only"}))


# ---------- OCR e Retrieval (backends simulados) ----------
class FakeOcr:
    def probe(self): return True, "ok"
    def read(self, image): return ["linha 1", "linha 2"]


class FakeClip:
    """Eixos: gato / carro. Imagem e texto no mesmo espaço."""
    def probe(self): return True, "ok"
    def embed_image(self, image):
        n = image.name
        return [1.0, 0.0] if "gato" in n else [0.0, 1.0] if "carro" in n else [0.5, 0.5]
    def embed_text(self, text): return [float("gato" in text), float("carro" in text)]


def svc(tmp_path, **kw):
    return build_service(Settings(media_dir=tmp_path / "media"), EmbProvider(), FakeVision(), None, None,
                         DocumentIndex(), ocr=kw.get("ocr", FakeOcr()), clip=kw.get("clip", FakeClip()))


def test_ocr_service(tmp_path):
    s = svc(tmp_path)
    (s.assets.root / "a.png").write_bytes(PNG)
    assert run(s.read_text("a.png")) == "linha 1\nlinha 2"
    s2 = svc(tmp_path, ocr=Down())
    from app.core.models import UnavailableError
    with pytest.raises(UnavailableError):
        run(s2.read_text("a.png"))


def test_retrieval_index_and_search_images(tmp_path):
    s = svc(tmp_path)
    d = s.assets.root / "fotos"
    d.mkdir()
    for n in ("gato1.png", "carro1.png"):
        (d / n).write_bytes(PNG + n.encode())
    (d / "falso.png").write_bytes(b"nao e imagem")
    with pytest.raises(Exception, match="não é image"):
        run(s.index_images("fotos/falso.png"))             # pedido direto: o erro é a resposta
    r = run(s.index_images("fotos"))                       # em pasta: o arquivo ruim é ignorado e relatado
    assert r["files"] == 2 and r["new"] == 2 and r["images"] == 2
    assert len(r["skipped"]) == 1 and "falso.png" in r["skipped"][0]
    assert run(s.index_images("fotos"))["new"] == 0         # idempotente
    assert run(s.search_images("um gato", 2))[0]["path"] == "fotos/gato1.png"
    assert run(s.search_images("um carro", 1))[0]["path"] == "fotos/carro1.png"


# ---------- Planner ----------
ALLOWED = {"lang_detect", "ocr_extract", "chat"}


def test_validate_plan_rules():
    ok = [{"action": "ocr_extract", "payload": {"path": "a.png"}}, {"action": "lang_detect", "payload": {"text": "{{prev}}"}}]
    assert validate_plan(ok, ALLOWED) == ok
    bad = [
        [], "x", [{"action": "chat"}] * (MAX_STEPS + 1),
        [{"action": "plan_run", "payload": {}}],                      # recursão
        [{"action": "rm_rf", "payload": {}}],                         # fora da lista
        [{"action": "chat", "payload": "texto"}],                     # payload inválido
        [{"action": "chat", "payload": {}, "shell": "ls"}],           # campo extra
        ["chat"],
    ]
    for b in bad:
        with pytest.raises(PlanError):
            validate_plan(b, ALLOWED)
    with pytest.raises(PlanError):
        validate_plan([{"action": "chat", "payload": {"text": "x" * 9000}}], ALLOWED)


def test_parse_plan_json():
    assert parse_plan_json('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert parse_plan_json('[1]') == [1]
    with pytest.raises(PlanError):
        parse_plan_json("não é json")


class PlanProvider:
    name = "p"
    def __init__(self, reply): self.reply = reply
    async def generate(self, model, prompt, system=None):
        self.system = system
        return self.reply
    async def list_models(self): return ["m"]
    async def loaded_models(self): return []


def planner(reply, steps_runner=None, actions=("lang_detect", "ocr_extract")):
    from app.core.registry import AgentRegistry
    from tests.test_stability import Slow
    reg = AgentRegistry()
    for a in actions:
        reg.register(Slow(f"ag_{a}", a))
    ctx = RunContext()
    ctx.run_step = steps_runner
    return PlannerAgent(PlanProvider(reply), "m", reg, ctx), ctx


def test_plan_create_proposes_validated_json_and_never_executes():
    ran = []

    async def runner(a, p): ran.append(a); return "x"
    good = json.dumps([{"action": "ocr_extract", "payload": {"path": "a.png"}}])
    pl, _ = planner(good, runner)
    out = run(pl.run("plan_create", {"text": "leia a imagem"}))
    assert json.loads(out)[0]["action"] == "ocr_extract" and ran == []
    assert "ocr_extract" in pl.provider.system and "plan_run" not in pl.provider.system
    pl2, _ = planner('[{"action":"apagar_tudo","payload":{}}]', runner)
    with pytest.raises(PlanError):
        run(pl2.run("plan_create", {"text": "x"}))
    pl3, _ = planner("claro, aqui vai o plano!", runner)
    with pytest.raises(OutputError):
        run(pl3.run("plan_create", {"text": "x"}))


def test_plan_run_chains_prev_and_stops_at_first_error():
    calls = []

    async def runner(action, payload):
        calls.append((action, payload))
        if action == "ocr_extract":
            return "texto do ocr"
        raise RuntimeError("falhou aqui")
    pl, _ = planner("", runner)
    steps = [{"action": "ocr_extract", "payload": {"path": "a.png"}},
             {"action": "lang_detect", "payload": {"text": "{{prev}}", "k": 3}},
             {"action": "ocr_extract", "payload": {"path": "nunca.png"}}]
    out = run(pl.run("plan_run", {"steps": steps}))
    assert calls[1] == ("lang_detect", {"text": "texto do ocr", "k": 3})
    assert len(calls) == 2 and "ERRO: falhou aqui" in out and "interrompido no passo 2 de 3" in out
    with pytest.raises(PlanError):
        run(pl.run("plan_run", {"steps": [{"action": "plan_run", "payload": {}}]}))


def test_plan_run_without_executor_is_an_error():
    pl, _ = planner("", None)
    with pytest.raises(PlanError):
        run(pl.run("plan_run", {"steps": [{"action": "lang_detect", "payload": {"text": "x"}}]}))


# ---------- Planner dentro do app: sem deadlock com 1 slot, RAM e limites ----------
class P:
    name = "p"
    async def generate(self, model, prompt, system=None): return "r"
    async def list_models(self): return ["qwen2.5:0.5b", "qwen2.5-coder:0.5b"]
    async def loaded_models(self): return []


def app_client(tmp_path, **kw):
    s = Settings(state_path=tmp_path / "s.db", media_dir=tmp_path / "m", max_concurrent=1, job_timeout=5)
    return make_client(create_app(s, provider=P(), memory=kw.get("memory", mem(avail=8000, total=8000))))


def test_api_plan_run_with_single_slot_does_not_deadlock(tmp_path):
    c = app_client(tmp_path)
    steps = [{"action": "lang_detect", "payload": {"text": "The cat is on the table and it is not happy"}},
             {"action": "chat", "payload": {"text": "idioma: {{prev}}"}}]
    r = c.post("/run", json={"action": "plan_run", "payload": {"steps": steps}})
    assert r.status_code == 200, r.text
    out = r.json()["output"]
    assert "1. lang_detect → en" in out and "2. chat → r" in out


def test_api_plan_errors_map_to_http(tmp_path):
    c = app_client(tmp_path)
    bad = c.post("/run", json={"action": "plan_run", "payload": {"steps": [{"action": "plan_run", "payload": {}}]}})
    assert bad.status_code == 422 and "si mesmo" in bad.json()["detail"]


def test_api_plan_step_rejected_when_ram_is_short(tmp_path):
    # planner (64 MB) cabe e reserva; sobram 36 MB e 'chat' (64 MB) é recusado: o plano relata onde parou
    c = app_client(tmp_path, memory=mem(avail=100, total=8000))
    r = c.post("/run", json={"action": "plan_run", "payload": {"steps": [{"action": "chat", "payload": {"text": "oi"}}]}})
    assert r.status_code == 200 and "ERRO" in r.json()["output"] and "RAM insuficiente" in r.json()["output"]


def test_ten_agents_registered_with_real_availability(tmp_path):
    c = app_client(tmp_path)
    a = {x["name"]: x for x in c.get("/agents").json()}
    assert len(a) == 10 and a["langid"]["available"] is True
    assert a["ocr"]["available"] is False and "paddleocr" in a["ocr"]["reason"]
    assert a["retrieval"]["available"] is False
