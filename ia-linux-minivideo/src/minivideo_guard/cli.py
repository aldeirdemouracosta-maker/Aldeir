"""CLI ``minivideo-guard`` — Hardware Safety Guard somente leitura."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import List, Optional

from .actions import ActionDispatcher, ProcessJobControl
from .monitor import GuardMonitor, JobLog
from .policy import DEFAULT_CONFIG, GuardPolicy, load_config
from .sensors import AmdgpuSysfsBackend, NvidiaSmiBackend, METRICS

UNITS = {"_c": "°C", "_pct": "%", "_mib": "MiB", "_w": "W", "_rpm": "RPM", "_mhz": "MHz"}


def _unit(key: str) -> str:
    return next((u for suffix, u in UNITS.items() if key.endswith(suffix)), "")


def _pairs(args) -> List[tuple]:
    backends = []
    if args.backend in ("auto", "amdgpu"):
        backends.append(AmdgpuSysfsBackend(args.sysfs_root))
    if args.backend in ("auto", "nvidia"):
        backends.append(NvidiaSmiBackend())
    pairs = [(b, d) for b in backends for d in b.discover()]
    if args.device:
        pairs = [(b, d) for b, d in pairs if d.id == args.device or d.id.endswith(":" + args.device)]
    return pairs


def _print_reading(reading) -> None:
    print(f"[{reading.device_id}]")
    for key in METRICS:
        value = reading.metrics[key]
        shown = "indisponível" if value is None else f"{value:.1f} {_unit(key)}".rstrip()
        print(f"  {key:<16} {shown}")
    for err in reading.errors:
        print(f"  aviso: {err}")


def cmd_detect(args) -> int:
    pairs = _pairs(args)
    if args.json:
        out = [dict(vars(d), sensores_indisponiveis=b.read(d).unavailable) for b, d in pairs]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if not pairs:
        print("Nenhuma GPU AMD (sysfs) ou NVIDIA (nvidia-smi) encontrada.")
        return 1
    for b, d in pairs:
        r = b.read(d)
        print(f"{d.id}: vendor={d.vendor} device={d.pci_device} slot={d.pci_slot} driver={d.driver} {d.name or ''}")
        disp = [k for k in METRICS if k not in r.unavailable]
        print(f"  sensores disponíveis:   {', '.join(disp) or 'nenhum'}")
        print(f"  sensores indisponíveis: {', '.join(r.unavailable) or 'nenhum'}")
        for err in r.errors:
            print(f"  aviso: {err}")
    return 0


def cmd_sample(args) -> int:
    pairs = _pairs(args)
    if not pairs:
        print("Nenhuma GPU encontrada.", file=sys.stderr)
        return 1
    readings = [b.read(d) for b, d in pairs]
    if args.json:
        print(json.dumps([r.to_dict() for r in readings], ensure_ascii=False, indent=2))
    else:
        for r in readings:
            _print_reading(r)
    return 0


def _single(args):
    pairs = _pairs(args)
    if not pairs:
        return None
    if len(pairs) > 1 and not args.device:
        print(f"Várias GPUs; monitorando {pairs[0][1].id}. Use --device para escolher.", file=sys.stderr)
    return pairs[0]


def _report(result) -> None:
    d = result["decisao"]
    m = result["leitura"].metrics
    temp = m["temp_edge_c"]
    line = f"nível={d.name:<8} borda={'n/d' if temp is None else f'{temp:.0f}°C'}"
    if d.reasons:
        line += "  " + "; ".join(d.reasons)
    for ev in result["eventos"]:
        line += f"  [ação {ev['acao']} ok={ev['ok']}]"
    print(line, flush=True)


def cmd_watch(args) -> int:
    pair = _single(args)
    if pair is None:
        print("Nenhuma GPU encontrada.", file=sys.stderr)
        return 1
    log = JobLog(args.log_dir, args.job_id) if args.job_id else None
    mon = GuardMonitor(pair[0], pair[1], GuardPolicy(load_config(args.config)), None, log, args.interval)
    try:
        mon.run(lambda: True, max_samples=args.count, on_step=_report)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_run(args) -> int:
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("Informe o comando do job após '--'.", file=sys.stderr)
        return 2
    policy = GuardPolicy(load_config(args.config))
    pair = _single(args)
    log = JobLog(args.log_dir, args.job_id)
    if pair is None and not args.permitir_sem_gpu:
        print("Nenhuma GPU monitorável; use --permitir-sem-gpu para executar sem proteção.", file=sys.stderr)
        return 2
    proc = subprocess.Popen(command, start_new_session=True)
    log.write("inicio", comando=command, pid=proc.pid, dispositivo=pair[1].id if pair else None)
    if pair is None:
        log.write("evento", mensagem="executado sem monitor: nenhuma GPU encontrada")
        return proc.wait()
    dispatcher = ActionDispatcher(ProcessJobControl(proc))
    mon = GuardMonitor(pair[0], pair[1], policy, dispatcher, log, args.interval)
    try:
        mon.run(lambda: proc.poll() is None, on_step=_report if args.verbose else None)
    except KeyboardInterrupt:
        ProcessJobControl(proc).stop("interrompido pelo usuário")
    code = proc.wait()
    log.write("fim", codigo=code, encerrado_pelo_guard=dispatcher.stopped)
    if dispatcher.stopped:
        print("Job encerrado pelo Safety Guard (condição crítica). Veja o log.", file=sys.stderr)
        return 3
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="minivideo-guard",
                                description="Hardware Safety Guard do IA-Linux MiniVideo (somente leitura, sem root).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--backend", choices=("auto", "amdgpu", "nvidia"), default="auto")
    common.add_argument("--device", help="ex.: amdgpu:card0, card0 ou nvidia:0")
    common.add_argument("--sysfs-root", default="/sys", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("detect", parents=[common], help="lista GPUs e sensores disponíveis/indisponíveis")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("sample", parents=[common], help="uma leitura de todos os sensores")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_sample)

    s = sub.add_parser("watch", parents=[common], help="monitora e mostra decisões (sem agir)")
    s.add_argument("--interval", type=float, default=2.0)
    s.add_argument("--count", type=int)
    s.add_argument("--config")
    s.add_argument("--job-id")
    s.add_argument("--log-dir", default="guard-logs")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("run", parents=[common], help="executa um job protegido: minivideo-guard run --job-id X -- cmd ...")
    s.add_argument("--job-id", required=True)
    s.add_argument("--interval", type=float, default=2.0)
    s.add_argument("--config")
    s.add_argument("--log-dir", default="guard-logs")
    s.add_argument("--permitir-sem-gpu", action="store_true")
    s.add_argument("--verbose", action="store_true")
    s.add_argument("command", nargs=argparse.REMAINDER)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("default-config", help="imprime a configuração padrão (JSON)")
    s.set_defaults(func=lambda a: print(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2)) or 0)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
