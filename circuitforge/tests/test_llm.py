from llm.electronics_llm import ElectronicsLLM, _to_int, list_light_models


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, **kw):
        self.calls.append(kw)
        return {"message": {"content": self.content}}


def llm_with(content):
    llm = ElectronicsLLM()
    llm.client = FakeClient(content)
    return llm


def test_create_package_parses_json_and_tolerates_text():
    llm = llm_with('Aqui:\n{"name": "SOIC-8", "package_type": "SMD", "pins": "8 pinos", "pitch_mm": 1.27}')
    spec = llm.create_package("NE555")
    assert spec.name == "SOIC-8" and spec.pins == 8 and spec.pitch_mm == 1.27
    assert llm.client.calls[0]["format"] == "json"


def test_create_package_garbage_output_does_not_crash():
    spec = llm_with("sem json").create_package("X", pins=4)
    assert spec.pins == 4 and spec.package_type == "unknown"


def test_read_circuit():
    r = llm_with('{"summary": "filtro", "components": ["R1"], "topology": "RC"}').read_circuit("R1 a b 1k")
    assert r.summary == "filtro" and r.components == ["R1"]


def test_free_text_calls():
    llm = llm_with("ok")
    assert llm.generate_netlist("rc") == "ok"
    assert llm.explain_waveform("rc", {"Vpp": 1.0}) == "ok"
    assert llm.suggest_modification("rc", "mais ganho") == "ok"
    assert llm.analyze_circuit_photo("AAAA") == "ok"


def test_photo_error_is_reported_as_text():
    llm = ElectronicsLLM()

    class Boom:
        def chat(self, **kw):
            raise RuntimeError("sem modelo")

    llm.client = Boom()
    assert "sem modelo" in llm.analyze_circuit_photo("AAAA")


def test_to_int():
    assert _to_int("16-pin", 0) == 16 and _to_int(None, 3) == 3 and _to_int(7.0) == 7


def test_list_models_new_and_old_api(monkeypatch):
    import llm.electronics_llm as mod

    class C:
        def __init__(self, models):
            self.models = models

        def list(self):
            return {"models": self.models}

    for entry in ({"model": "qwen2:0.5b"}, {"name": "qwen2:0.5b"}):
        monkeypatch.setattr(mod.ollama, "Client", lambda host, e=entry: C([e]))
        assert list_light_models() == ["qwen2:0.5b"]
    monkeypatch.setattr(mod.ollama, "Client", lambda host: (_ for _ in ()).throw(OSError()))
    assert list_light_models() == []
