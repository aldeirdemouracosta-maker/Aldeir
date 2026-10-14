import json

import numpy as np
import pytest

from core.footprints import build_footprint
from core.library import get, REGISTRY
from core.simulator import CircuitSimulator
from core.spice_engine import SpiceError, ngspice_available, sanitize_netlist
from core.tutor import lesson_markdown, static_quiz
from llm import ElectronicsLLM, validate_netlist
from llm.parsing import parse_analysis, parse_creator_response, parse_si
from llm.retrieval import search_library

needs_spice = pytest.mark.skipif(not ngspice_available(), reason="ngspice não instalado")


# ------------------------------------------------------------- sanitização
def test_sanitize_removes_control_blocks():
    s = sanitize_netlist("T\nV1 a 0 1\nR1 a 0 1k\n.control\nshell rm -rf /\n.endc\n.tran 1u 1m\n.end")
    assert "shell" not in s.body and ".tran" not in s.body
    assert s.analyses and s.warnings


@pytest.mark.parametrize("bad", [
    "T\nV1 a 0 1\n.include /etc/passwd\nR1 a 0 1k",
    "T\nV1 a 0 PWL file=/etc/passwd\nR1 a 0 1k",
    "T\nV1 a 0 1\n.lib x.lib\nR1 a 0 1k",
])
def test_sanitize_rejects_file_access(bad):
    with pytest.raises(SpiceError):
        sanitize_netlist(bad)


def test_title_detection():
    assert sanitize_netlist("R1 a 0 1k\nV1 a 0 1").title == "CircuitForge"
    assert sanitize_netlist("Meu filtro RC\nR1 a 0 1k\nV1 a 0 1").title == "Meu filtro RC"


@needs_spice
def test_load_netlist_now_works():
    sim = CircuitSimulator()
    sim.load_netlist("Divisor\nV1 in 0 DC 10\nR1 in out 1k\nR2 out 0 1k\n.op\n.end")
    assert sim.run_operating_point()["out"] == pytest.approx(5.0)
    assert sim.detected_analyses == [".op"]


# ------------------------------------------------------------- parsing
def test_parse_si_and_analysis():
    assert parse_si("1meg") == 1e6 and parse_si("2.2u") == pytest.approx(2.2e-6) and parse_si("5m") == 5e-3
    a = parse_analysis("ac start=10 stop=1meg points=30")
    assert a == {"kind": "ac", "start": 10.0, "stop": 1e6, "points": 30}
    assert parse_analysis("lixo") is None


RESP = """TITULO: Filtro RC
ANALISE: tran stop=5m step=10u
SONDAS: in, out
```spice
Filtro RC
Vin in 0 SIN(0 1 1k)
R1 in out 1k
C1 out 0 100n
```
EXPLICACAO: Passa-baixa de 1,6 kHz."""


def test_parse_creator_response():
    p = parse_creator_response(RESP)
    assert p["titulo"] == "Filtro RC" and p["sondas"] == ["in", "out"] and "R1 in out" in p["netlist"]
    assert "1,6 kHz" in p["explicacao"]


# ------------------------------------------------------------- LLM falso
class FakeClient:
    """Responde em sequência e guarda as mensagens para inspeção."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, **kw):
        self.calls.append(kw)
        return {"message": {"content": self.replies.pop(0)}}


@needs_spice
def test_creator_first_attempt_ok():
    llm = ElectronicsLLM(client=FakeClient([RESP]))
    r = llm.create_circuit("filtro passa baixa rc")
    assert r.ok and r.attempts == 1 and r.analysis["kind"] == "tran"
    assert set(r.probes) == {"in", "out"}


@needs_spice
def test_creator_repairs_after_error_message():
    broken = RESP.replace("C1 out 0 100n", "C1 out 0 100n\nQ9 a b c MODELO_INEXISTENTE")
    fake = FakeClient([broken, RESP])
    r = ElectronicsLLM(client=fake).create_circuit("filtro rc")
    assert r.ok and r.attempts == 2
    assert "rejeitou" in fake.calls[1]["messages"][-1]["content"]   # erro foi devolvido ao modelo


@needs_spice
def test_creator_gives_up_with_library_fallback():
    fake = FakeClient(["não sei"] * 3)
    r = ElectronicsLLM(client=fake).create_circuit("pedal de overdrive para guitarra", max_attempts=3)
    assert not r.ok and r.fallback in REGISTRY and r.attempts == 3


@needs_spice
def test_creator_blocks_malicious_netlist():
    evil = RESP.replace("R1 in out 1k", ".control\nshell echo pwned\n.endc\nR1 in out 1k")
    r = ElectronicsLLM(client=FakeClient([evil])).create_circuit("filtro")
    assert r.ok and "shell" not in r.netlist and ".control" not in r.netlist


def test_ai_is_never_called_without_button():
    """Importar e usar biblioteca/tutor offline não deve instanciar cliente nem chamar Ollama."""
    fake = FakeClient([])
    c = get("rc_lowpass")
    assert lesson_markdown(c) and static_quiz(c)
    assert fake.calls == []


def test_quiz_parsing_and_static_quiz():
    good = json.dumps({"perguntas": [{"pergunta": "Q?", "opcoes": ["a", "b", "c", "d"], "correta": 2, "explicacao": "x"}]})
    llm = ElectronicsLLM(client=FakeClient(["texto solto", good]))
    q = llm.quiz(get("rc_lowpass"), get("rc_lowpass").defaults())
    assert q[0].correta == 2
    for it in static_quiz(get("buck_converter"), n=3):
        assert 0 <= it["correta"] < len(it["opcoes"]) and len(set(it["opcoes"])) == len(it["opcoes"])


def test_retrieval_finds_requested_topics():
    assert search_library("pedal de guitarra com distorção")[0][1].category == "guitarra"
    assert search_library("carregador de celular no carro")[0][1].category == "veiculos"
    assert search_library("painel solar sombra")[0][1].category == "solar"
    assert search_library("antena casamento de impedância")[0][1].category == "antenas"


def test_every_lesson_renders():
    for c in REGISTRY.values():
        md = lesson_markdown(c)
        assert c.name in md and "Objetivo" in md


# ------------------------------------------------------------- footprints
@pytest.mark.parametrize("name,pads", [("SOIC-8", 8), ("0805", 2), ("DIP-14", 14), ("TO-92", 3), ("QFN-32", 33), ("header 1x6", 6)])
def test_footprints(name, pads):
    fp = build_footprint(name)
    k = fp.to_kicad()
    assert len(fp.pads) == pads and k.count("(") == k.count(")") and "..." not in k


def test_package_via_llm_without_calling_model():
    fake = FakeClient([])
    pkg = ElectronicsLLM(client=fake).create_package("SOIC-8")
    assert pkg.pins == 8 and pkg.footprint_kicad.startswith("(footprint") and fake.calls == []


def test_units_roundtrip():
    from core.units import parse_si, to_si
    for x in (4.7e3, 100e-9, 1e6, 2.2e-6, 12.0, 0.5, 33e-12):
        assert parse_si(to_si(x)) == pytest.approx(x, rel=1e-3)
    assert to_si(4700) == "4.7k" and to_si(1e-7) == "100n" and to_si(1e6) == "1meg"


@needs_spice
def test_sweep_actually_changes_the_circuit():
    from automation import ParameterSweep, MonteCarlo
    from automation.metrics import peak_freq
    sw = ParameterSweep(get("series_rlc"))
    df = sw.run("c", [50e-9, 100e-9, 200e-9], analysis="AC (Bode)", measure_fn=peak_freq("out"))
    f = df["f_pico(out) [Hz]"].values
    assert f[0] > f[1] > f[2]                                       # mais C → ressonância mais baixa
    assert f[1] / f[2] == pytest.approx(np.sqrt(2), rel=0.1)
    mc = MonteCarlo(get("voltage_divider")).run({"r1": 0.05, "r2": 0.05}, n_runs=15, analysis="Ponto de operação",
                                                 measure_fn=lambda r: {"out": r["out"]})
    assert mc["out"].std() > 0 and mc["out"].mean() == pytest.approx(2.5, abs=0.1)
