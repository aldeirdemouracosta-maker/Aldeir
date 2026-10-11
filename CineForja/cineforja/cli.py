"""CLI interativo: python -m cineforja.cli start|resume <project_id>."""
from __future__ import annotations

import argparse
import sys

from .orchestrator.graph import build_app
from .orchestrator.hitl import CHECKPOINT_LABELS, config_for, current_state, pending_checkpoint, resume
from .orchestrator.state import new_state


def drive(app, project_id: str, auto_approve: bool = False) -> dict:
    while (node := pending_checkpoint(app, project_id)):
        state = current_state(app, project_id)
        print(f"\n== {CHECKPOINT_LABELS.get(node, node)} ==")
        for s in state.get("storyboard", []):
            print(f"  shot {s['index']}: {s['status']} score={s['score']} :: {s['prompt']}")
        if not auto_approve and input("Aprovar e continuar? [s/N] ").strip().lower() != "s":
            print("Pausado. Retome com: cineforja.cli resume", project_id)
            return state
        resume(app, project_id)
    return current_state(app, project_id)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cineforja")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("project_id")
    s.add_argument("brief")
    s.add_argument("--style", choices=["cgi", "stop_motion"], default="cgi")
    s.add_argument("--yes", action="store_true", help="aprova todos os pontos automaticamente")
    r = sub.add_parser("resume")
    r.add_argument("project_id")
    r.add_argument("--yes", action="store_true")
    p.add_argument("--db", default="data/cineforja.db")
    args = p.parse_args(argv)

    app = build_app(args.db)
    if args.cmd == "start":
        app.invoke(new_state(args.project_id, args.brief, args.style), config_for(args.project_id))
    final = drive(app, args.project_id, args.yes)
    if final.get("output_path"):
        print("\n".join(final["logs"]))
        print("\nSaída:", final["output_path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
