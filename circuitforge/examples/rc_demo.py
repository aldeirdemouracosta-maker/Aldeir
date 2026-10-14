"""Exemplo de uso como biblioteca: simula o filtro RC da biblioteca e mede a frequência de corte."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.library import get
from core.simulator import CircuitSimulator
from instruments import BodePlotter

cdef = get("rc_lowpass")
params = {"r": 1e3, "c": 100e-9}
sim = CircuitSimulator()
sim.load_circuit(cdef, params)

res = sim.run(cdef.analysis_options(params)["AC (Bode)"])
bode = BodePlotter()
bode.load(res)
fc = bode.find_cutoff("out")["f_high"]
teorico = cdef.theory_values(params)["Frequência de corte fc"][0]
print(f"fc simulada = {fc:.1f} Hz | fc teórica = {teorico:.1f} Hz")

# Também dá para simular um netlist qualquer (texto SPICE):
sim.load_netlist("Divisor\nV1 in 0 DC 10\nR1 in out 1k\nR2 out 0 3k\n")
print("Vout do divisor:", sim.run_operating_point()["out"], "V")
