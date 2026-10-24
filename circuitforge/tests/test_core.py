import json
import shutil

import numpy as np
import pytest

from core.netlist import get_builder, list_example_circuits
from core.simulator import CircuitSimulator
from core.ngspice_runner import NgSpiceError, parse_rawfile

pytestmark = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice ausente")


def make(name, **kw):
    sim = CircuitSimulator()
    sim.circuit = get_builder(name)(**kw)
    return sim


@pytest.mark.parametrize("name", list(list_example_circuits()))
def test_every_example_runs_all_analyses(name):
    sim = make(name)
    assert sim.run_operating_point()
    tran = sim.run_transient(1e-5, 2e-3)
    assert len(tran["time"]) > 10
    assert all(np.all(np.isfinite(v)) for v in tran.values())
    ac = sim.run_ac(10, 1e5, 5)
    assert len(ac["frequency"]) > 5


def test_voltage_divider_op():
    op = make("voltage_divider", r1=1e3, r2=3e3, vin=8.0).run_operating_point()
    assert op["out"] == pytest.approx(6.0, rel=1e-6)


def test_rc_lowpass_cutoff():
    from instruments.bode import BodePlotter

    sim = make("rc_lowpass", r_value=1e3, c_value=100e-9)
    b = BodePlotter()
    b.load(sim.run_ac(10, 1e6, 20))
    assert b.find_cutoff("out") == pytest.approx(1591.5, rel=0.02)


def test_inverting_opamp_gain():
    r = make("inverting_opamp").run_transient(1e-6, 5e-3)
    assert np.ptp(r["out"]) / np.ptp(r["in"]) == pytest.approx(10, rel=0.01)


def test_rectifiers():
    hw = make("halfwave_rectifier").run_transient(1e-5, 50e-3)["out"]
    assert hw.min() > -0.01 and 9.0 < hw.max() < 9.8
    fw = make("fullwave_bridge").run_transient(1e-5, 50e-3)["outp"]
    assert fw.min() > -0.01 and fw.max() > 8.0


def test_common_emitter_is_biased_and_amplifies():
    sim = make("common_emitter")
    op = sim.run_operating_point()
    assert 2.0 < op["collector"] < 11.0  # região ativa
    r = sim.run_transient(1e-6, 10e-3)
    mask = r["time"] > 5e-3
    gain = np.ptp(r["collector"][mask]) / np.ptp(r["in"][mask])
    assert 5 < gain < 12


def test_555_frequency():
    from instruments.scope import Oscilloscope

    r = make("astable_555", r_a=10e3, r_b=10e3, c=100e-9).run_transient(1e-6, 20e-3)
    o = Oscilloscope()
    o.load(r)
    assert o.measure("out")["Freq_Hz"] == pytest.approx(1.44 / (30e3 * 100e-9), rel=0.05)


def test_biodigester_thermostat_switches():
    cold = make("biodigester_control", setpoint_c=37, ambient_c=20).run_operating_point()
    hot = make("biodigester_control", setpoint_c=37, ambient_c=40).run_operating_point()
    assert cold["heater_node"] < 1.0   # aquecedor ligado
    assert hot["heater_node"] > 20.0   # aquecedor desligado


def test_dc_sweep():
    d = make("voltage_divider").run_dc_sweep("Vin", 0, 5, 1)
    assert d["out"] == pytest.approx(d["sweep"] / 2)


def test_load_netlist_text():
    sim = CircuitSimulator()
    sim.load_netlist("Divisor\nV1 a 0 10\nR1 a b 1k\nR2 b 0 1k\n.end")
    assert sim.run_operating_point()["b"] == pytest.approx(5.0)
    sim.load_netlist("* comentario\nV1 a 0 SIN(0 1 1k)\nR1 a b 1k\nC1 b 0 1u")
    assert len(sim.run_ac(10, 1e4, 5)["frequency"]) > 5


def test_errors_are_reported():
    sim = CircuitSimulator()
    with pytest.raises(RuntimeError):
        sim.run_operating_point()
    sim.load_netlist("bad\nV1 a 0 1\nX1 a b nosub\n")  # subcircuito inexistente
    with pytest.raises(NgSpiceError):
        sim.run_transient(1e-6, 1e-4)
    with pytest.raises(ValueError):
        make("voltage_divider").run_dc_sweep("Nope", 0, 1, 0.5)
    with pytest.raises(ValueError):
        sim.load_netlist("  ")


def test_parse_ascii_rawfile():
    raw = (
        b"Title: t\nPlotname: Operating Point\nFlags: real\nNo. Variables: 2\nNo. Points: 1\n"
        b"Variables:\n\t0\tv(a)\tvoltage\n\t1\tv(b)\tvoltage\nValues:\n 0\t1.5\n\t2.5\n"
    )
    r = parse_rawfile(raw)
    assert r["v(a)"][0] == 1.5 and r["v(b)"][0] == 2.5


def test_sweep_uses_value():
    from automation.sweep import ParameterSweep

    def factory(r):
        s = CircuitSimulator()
        s.circuit = get_builder("rc_lowpass")(r_value=r, c_value=100e-9)
        return s

    df = ParameterSweep(factory).sweep_transient(
        "R", [100, 1e3, 1e4], 1e-5, 5e-3,
        measure_fn=lambda res: {"vpp": float(np.ptp(res["out"]))},
    )
    assert df["vpp"].is_monotonic_decreasing and df["vpp"].nunique() == 3


def test_montecarlo_varies_results():
    from automation.montecarlo import MonteCarlo

    def factory(p):
        s = CircuitSimulator()
        s.circuit = get_builder("voltage_divider")(r1=p["r1"], r2=p["r2"], vin=5.0)
        return s

    mc = MonteCarlo(factory)
    df = mc.run(
        {"r1": 1e3, "r2": 1e3}, {"r1": 0.05, "r2": 0.05}, n_runs=10,
        analysis="op", measure_fn=lambda r: {"vout": r["out"]},
    )
    assert len(df) == 10 and df["vout"].std() > 0
    assert df["vout"].mean() == pytest.approx(2.5, abs=0.1)


def test_modifier_presets_simulate():
    from core.modifier import MODIFICATION_PRESETS, apply_preset

    for pid in MODIFICATION_PRESETS:
        orig, mod, meta = apply_preset(pid)
        for c in (orig, mod):
            s = CircuitSimulator()
            s.circuit = c
            assert s.run_operating_point()
            assert len(s.run_transient(1e-5, 2e-3)["time"]) > 10
        assert meta.title


def test_dataset_valid():
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "finetune/dataset/electronics_sft.jsonl"
    for line in p.read_text().splitlines():
        msgs = json.loads(line)["messages"]
        assert {m["role"] for m in msgs} >= {"user", "assistant"}
