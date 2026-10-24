"""
Exemplo de uso programático do CircuitForge (sem Streamlit).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.simulator import CircuitSimulator
from core.netlist import build_rc_lowpass
from instruments.scope import Oscilloscope
from instruments.bode import BodePlotter

def main():
    print("=== CircuitForge – Demo RC Low-Pass ===\n")

    # 1. Monta o circuito
    circuit = build_rc_lowpass(r_value=1e3, c_value=100e-9, vin_amplitude=1.0, vin_freq=1e3)

    # 2. Simulador
    sim = CircuitSimulator("RC Low-Pass Demo")
    sim.circuit = circuit

    # 3. Transient
    print("Rodando transient...")
    result_t = sim.run_transient(step_time=1e-6, end_time=5e-3)
    scope = Oscilloscope()
    scope.load(result_t)
    meas = scope.measure("out")
    print("Medições no nó 'out':")
    for k, v in meas.items():
        print(f"  {k}: {v:.4g}")

    # 4. AC / Bode
    print("\nRodando análise AC...")
    result_ac = sim.run_ac(start_freq=10, stop_freq=1e5, points_per_decade=20)
    bode = BodePlotter()
    bode.load(result_ac)
    fc = bode.find_cutoff("out")
    print(f"Frequência de corte aproximada (-3 dB): {fc:.1f} Hz" if fc else "Cutoff não encontrado")

    print("\nDemo concluída. Use a interface Streamlit para gráficos interativos.")

if __name__ == "__main__":
    main()
