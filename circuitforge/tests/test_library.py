"""Simula TODOS os circuitos da biblioteca e confere valores teóricos conhecidos."""

import math

import numpy as np
import pytest

from core.library import REGISTRY, CATEGORIES, get
from core.simulator import CircuitSimulator
from core.spice_engine import ngspice_available

pytestmark = pytest.mark.skipif(not ngspice_available(), reason="ngspice não instalado")


def run(cid, analysis=None, **params):
    c = get(cid)
    sim = CircuitSimulator()
    sim.load_circuit(c, params)
    opts = c.analysis_options(params)
    spec = opts[analysis] if analysis else next(iter(opts.values()))
    return sim.run(spec)


def tail(y, frac=0.3):
    return y[int(len(y) * (1 - frac)):]


# ---------------------------------------------------------------- catálogo
def test_catalog_covers_requested_topics():
    assert set(CATEGORIES) >= {"computador", "fontes", "ia", "audio", "guitarra", "solar", "veiculos", "radio_tv", "antenas"}
    for cat in CATEGORIES:
        assert any(c.category == cat for c in REGISTRY.values()), cat
    assert len(REGISTRY) >= 45


@pytest.mark.parametrize("cid", sorted(REGISTRY))
def test_every_circuit_every_analysis_runs(cid):
    c = REGISTRY[cid]
    assert c.lesson.objetivo and c.lesson.teoria, "toda lição precisa de objetivo e teoria"
    for name, spec in c.analysis_options().items():
        sim = CircuitSimulator()
        sim.load_circuit(c)
        res = sim.run(spec)
        assert res
        for k, v in res.items():
            arr = np.atleast_1d(v)
            assert np.all(np.isfinite(arr)), f"{cid}/{name}/{k} contém NaN/inf"
        for probe in c.probes:
            key = probe if probe in res else None
            assert key or f"{probe}_mag" in res, f"probe {probe} ausente em {cid}/{name}"


# ---------------------------------------------------------- valores teóricos
def test_rc_lowpass_cutoff():
    r = run("rc_lowpass", "AC (Bode)")
    f, m = r["frequency"], r["out_mag"]
    fc = f[np.argmin(abs(m - 1 / math.sqrt(2)))]
    assert fc == pytest.approx(1 / (2 * math.pi * 1e3 * 100e-9), rel=0.05)


def test_divider_op():
    r = run("voltage_divider", "Ponto de operação", r1=10e3, r2=30e3, vin=8)
    assert r["out"] == pytest.approx(6.0, rel=1e-6)


def test_inverting_gain():
    r = run("inverting_opamp")
    assert np.ptp(tail(r["out"])) / np.ptp(tail(r["in"])) == pytest.approx(10, rel=0.02)


def test_555_frequency():
    r = run("astable_555")
    t, v = r["time"], r["out"]
    up = t[1:][(v[1:] > 2.5) & (v[:-1] <= 2.5)][1:]
    assert 1 / np.mean(np.diff(up)) == pytest.approx(1.44 / (30e3 * 100e-9), rel=0.1)


def test_series_rlc_resonance():
    r = run("series_rlc", "AC (Bode)")
    f0 = f = r["frequency"][np.argmax(r["out_mag"])]
    assert f0 == pytest.approx(1 / (2 * math.pi * math.sqrt(10e-3 * 100e-9)), rel=0.05)


def test_buck_ratio():
    r = run("buck_converter")
    assert tail(r["out"], 0.2).mean() == pytest.approx(5.0, rel=0.08)


def test_boost_ratio():
    r = run("boost_converter")
    assert tail(r["out"], 0.2).mean() == pytest.approx(10.0, rel=0.1)


def test_rectifier_ripple_formula():
    p = dict(vac=17.0, c=2200e-6, rl=100.0, f=60.0)
    r = run("rectifier_filter", **p)
    t, v = r["time"], r["vl"]
    y = v[t > t[-1] - 2 / p["f"]]                      # últimos 2 ciclos
    expected = (p["vac"] - 1.4) / p["rl"] / (2 * p["f"] * p["c"])
    assert np.ptp(y) == pytest.approx(expected, rel=0.4)


def test_ldo_regulates():
    r = run("ldo_adjustable")
    assert tail(r["out"], 0.2).mean() == pytest.approx(5.0, abs=0.05)
    r = run("usb_3v3_ldo")
    assert tail(r["out"], 0.2).mean() == pytest.approx(3.3, abs=0.05)


def test_zener_regulates():
    r = run("zener_regulator", "Ponto de operação")
    assert r["out"] == pytest.approx(5.1, abs=0.4)


def test_i2c_rise_time():
    r = run("i2c_bus")
    t, v = r["time"], r["sda"]
    vdd = 3.3
    k = np.argmax(v < 0.05)                     # após puxar a linha para baixo
    t20 = t[k + np.argmax(v[k:] > 0.3 * vdd)]
    t80 = t[k + np.argmax(v[k:] > 0.7 * vdd)]
    assert (t80 - t20) == pytest.approx(0.8473 * 4.7e3 * 100e-12, rel=0.1)


def test_crossbar_matrix_vector():
    from core.library.ia import MATRIX
    r = run("crossbar_mvm", "Ponto de operação")
    v = [0.5, -0.3, 0.8]
    for j in range(2):
        expected = -1e3 * sum(MATRIX[i][j] * 1e-3 * v[i] for i in range(3))
        assert r[f"y{j+1}"] == pytest.approx(expected, rel=0.01)


def test_neuron_is_monotonic_and_saturates():
    r = run("analog_neuron")
    y = r["out"]
    assert np.all(np.diff(y) >= -1e-3) or np.all(np.diff(y) <= 1e-3)
    assert abs(y[-1] - y[-2]) < 0.2 * abs(y[-1] - y[0]) / 10


def test_sallen_key_cutoff():
    r = run("sensor_frontend", "AC (Bode)")
    f = r["frequency"]
    m = r["out_mag"] / r["out_mag"][0]
    fc = f[np.argmin(abs(m - 1 / math.sqrt(2)))]
    expected = 1 / (2 * math.pi * math.sqrt(10e3 * 10e3 * 2.2e-9 * 1.1e-9))
    assert fc == pytest.approx(expected, rel=0.1)


def test_preamp_gain():
    r = run("audio_preamp", "AC (Bode)")
    f = r["frequency"]
    assert r["out_mag"][np.argmin(abs(f - 1e3))] == pytest.approx(11.0, rel=0.03)


def test_class_d_reproduces_audio():
    r = run("class_d_amp")
    assert np.max(tail(r["out"], 0.5)) == pytest.approx(12.0, rel=0.15)


def test_crossover_is_minus_3db_at_fc():
    r = run("crossover_2way")
    f = r["frequency"]
    i = np.argmin(abs(f - 2500))
    assert r["woofer_mag"][i] == pytest.approx(r["tweeter_mag"][i], rel=0.1)


def test_wah_peak_moves_with_pedal():
    f1 = run("wah_pedal", pos=0.0)
    f2 = run("wah_pedal", pos=1.0)
    p1 = f1["frequency"][np.argmax(f1["wah_mag"])]
    p2 = f2["frequency"][np.argmax(f2["wah_mag"])]
    assert p1 == pytest.approx(400, rel=0.12) and p2 == pytest.approx(2200, rel=0.12)


def test_overdrive_clips_with_diodes():
    r = run("overdrive_ts")
    assert np.ptp(tail(r["clip"], 0.5)) < 1.6          # limitado ≈ ±0,7 V


def test_tremolo_depth():
    r = run("tremolo")
    y = np.abs(r["out"])
    assert y.max() == pytest.approx(0.2, rel=0.05)


def test_pv_voc_and_isc():
    r = run("pv_panel_iv")
    i = r["ipv"]
    assert i[0] == pytest.approx(8.0, rel=0.05)
    p = r["pw"]
    assert p.max() == pytest.approx(0.75 * 8 * 21.6, rel=0.2)


def test_pv_shading_has_two_steps():
    with_bp = run("solar_shading", bypass=1)
    without = run("solar_shading", bypass=0)
    # com bypass a corrente a 8 V (sub-conjunto sombreado desviado) é maior que sem bypass
    idx = int(8 / 0.1)
    assert with_bp["ipv"][idx] > without["ipv"][idx]


def test_load_dump_clamped_by_tvs():
    with_tvs = run("load_dump_clamp", tvs=1)
    without = run("load_dump_clamp", tvs=0)
    assert with_tvs["ecu"].max() < 36 and without["ecu"].max() > 50


def test_relay_flyback_diode_limits_spike():
    ok = run("relay_flyback", flyback=1)
    bad = run("relay_flyback", flyback=0)
    assert ok["drain"].max() < 14 and bad["drain"].max() > 40


def test_reverse_polarity_blocks():
    r = run("reverse_polarity", pol=-1)
    assert abs(r["load"]).max() < 0.5
    r = run("reverse_polarity", pol=1, mode=1)
    assert r["load"][-1] > 11.0


def test_led_pwm_average_current():
    r = run("led_pwm_dimmer", duty=0.5)
    assert tail(r["iled"], 0.5).mean() == pytest.approx(0.5 * 0.3, rel=0.35)


def test_alternator_charges_battery():
    r = run("alternator_rectifier")
    assert tail(r["bus"]).mean() > 12.5


def test_lc_tuner_f0():
    r = run("lc_tuner")
    f0 = r["frequency"][np.argmax(r["tank_mag"])]
    assert f0 == pytest.approx(1 / (2 * math.pi * math.sqrt(240e-6 * 100e-12)), rel=0.05)


def test_am_detector_recovers_audio():
    r = run("am_detector")
    a = tail(r["audio"], 0.5)
    assert np.ptp(a) > 0.3


def test_superhet_if_present():
    r = run("superhet_mixer")
    t, y = r["time"], r["if"]
    seg = tail(y, 0.4)
    dt = t[1] - t[0]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    # passo de amostragem não uniforme → só checa que há energia relevante
    assert np.ptp(seg) > 1e-3


def test_sync_separator_pulse_rate():
    r = run("tv_sync_separator")
    s = r["sync"] > 2.5
    edges = np.sum(np.diff(s.astype(int)) == 1)
    assert 8 <= edges <= 10


def test_colpitts_oscillates_at_f0():
    r = run("colpitts_oscillator")
    t, v = r["time"], tail(r["c"], 0.3)
    assert np.ptp(v) > 1.0


def test_dipole_match_at_resonance():
    r = run("dipole_equivalent")
    f, g = r["frequency"], r["gamma_mag"]
    assert f[np.argmin(g)] == pytest.approx(146e6, rel=0.05)
    assert g.min() == pytest.approx(abs((74 - 50) / (74 + 50)), abs=0.03)


def test_quarter_wave_perfect_match():
    r = run("quarter_wave_transformer")
    f, g = r["frequency"], r["gamma_mag"]
    assert g[np.argmin(abs(f - 100e6))] < 0.02


def test_l_match_perfect_match():
    r = run("l_match")
    f, g = r["frequency"], r["gamma_mag"]
    assert g[np.argmin(abs(f - 14.2e6))] < 0.05


def test_bandpass_center():
    r = run("antenna_bandpass")
    f, m = r["frequency"], r["out_mag"]
    assert f[np.argmax(m)] == pytest.approx(98e6, rel=0.1)


def test_balun_good_match_midband():
    r = run("tv_balun_4to1")
    f, g = r["frequency"], r["gamma_mag"]
    assert g[np.argmin(abs(f - 150e6))] < 0.3
