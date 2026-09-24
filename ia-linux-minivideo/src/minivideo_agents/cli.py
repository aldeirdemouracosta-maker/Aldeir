"""CLI ``minivideo-agentes``: dispositivos, agentes, plano e execução."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

from . import devices as devmod
from .executor import Executor
from .planner import explain, plan_rules
from .registry import route_all
from .workspace import Workspace

TOOL_DIRS = ["/usr/libexec/minivideo"]


def context(args):
    ws = Workspace(args.workspace)
    devs = devmod.detect()
    assigns = {a.agent.id: a for a in route_all(devs, ws.models_dirs, TOOL_DIRS)}
    return ws, devs, assigns


def cmd_dispositivos(args) -> int:
    _, devs, _ = context(args)
    for d in devs:
        vram = f"{d.vram_mib} MiB" if d.vram_mib else "-"
        print(f"{d.id:<16} {d.kind:<12} {'usável' if d.usable else 'inutilizável':<13} {vram:<10} {d.name}")
        for note in d.notes:
            print(f"{'':<16} - {note}")
    return 0


def cmd_agentes(args) -> int:
    _, _, assigns = context(args)
    if args.json:
        print(json.dumps([{"agente": a.agent.id, "disponivel": a.disponivel,
                           "dispositivo": a.device.id if a.device else None,
                           "ferramenta": a.ferramenta, "motivos": a.motivos, "estado": a.agent.estado}
                          for a in assigns.values()], ensure_ascii=False, indent=2))
        return 0
    for a in assigns.values():
        mark = "OK " if a.disponivel else "-- "
        dev = a.device.id if a.device else "nenhum"
        print(f"{mark}{a.agent.nome:<20} [{a.agent.estado}] dispositivo={dev}")
        for m in a.motivos:
            print(f"      {m}")
    return 0


def cmd_plano(args) -> int:
    _, _, assigns = context(args)
    print(explain(plan_rules(args.pedido), assigns))
    return 0


def cmd_executar(args) -> int:
    ws, _, assigns = context(args)
    plan = plan_rules(args.pedido)
    print(explain(plan, assigns))
    if not args.confirmar:
        print("\nUse --confirmar para executar.")
        return 0
    res = Executor(ws, assigns, guard=not args.sem_guard).run(plan, args.entrada, args.saida, args.job_id)
    print()
    if res.ok:
        print(f"Concluído: {res.saida} (job {res.job_id}; log em {ws.logs})")
        for e in res.etapas:
            if "agente" in e:
                print(f"  {e['agente']:<14} {e['segundos']:>7.1f} s")
            else:
                for n in e.get("notas", []):
                    print(f"  nota: {n}")
        return 0
    print(f"Falhou: {res.erro} (job {res.job_id})", file=sys.stderr)
    return 1


def cmd_motores(args) -> int:
    from minivideo_especialistas.motores import matriz_texto
    print(matriz_texto())
    return 0


def cmd_schemas(args) -> int:
    import shutil as _sh
    from minivideo_especialistas import schema
    for nome in ("diretor", "editor", "fiscal", "continuista", "job"):
        path = f"{schema.SCHEMA_DIR}/{nome}.schema.json"
        if args.exportar:
            import os as _os
            _os.makedirs(args.exportar, exist_ok=True)
            _sh.copy(path, args.exportar)
        print(path)
    return 0


def _resumo_especialistas(pl, executar: bool = False) -> str:
    d, e, f = pl.diretor, pl.editor, pl.fiscal
    out = [f"Job {pl.job_id} · orquestrador: {pl.modo} (Diretor={d['origem']}, Editor={e['origem']})", "",
           "DIRETOR — cenas e critérios"]
    for c in d["cenas"]:
        faixa = "vídeo inteiro" if c["inicio_s"] is None else f"{c['inicio_s']:.2f}–{c['fim_s']:.2f} s"
        out.append(f"  {c['id']}: {faixa} · objetivos: {', '.join(c['objetivos']) or '(nenhum)'}")
    for k in d["criterios"]:
        out.append(f"  critério {k['id']} [{k['cena']}] {k['tipo']} = {k['alvo']} (±{k['tolerancia']})")
    out += [f"  aviso: {a}" for a in d["avisos"]]
    out += ["", "EDITOR — operações e motores cadastrados"]
    for op in e["operacoes"]:
        params = ", ".join(f"{k}={v}" for k, v in op["params"].items() if k != "prompt")
        out.append(f"  {op['cena']}: {op['agente']:<14} motor={op['motor']:<24} {params}")
    for r in e["rejeitados"]:
        out.append(f"  REJEITADO {r['cena']}/{r['objetivo']}: {r['motivo']}")
    out += ["", f"FISCAL DE HARDWARE — decisão: {f['decisao'].upper()}"]
    rec = f["recursos"]
    out.append(f"  RAM disponível: {rec['ram_disponivel_mib']} MiB · disco livre: {rec['disco_livre_mib']} MiB "
               f"· estimativa de disco: {rec['estimativa_disco_mib']} MiB · GPU: "
               f"{(rec['gpu'] or {}).get('dispositivo', 'sem sensores')}")
    out += [f"  - {m}" for m in f["motivos"]]
    for t in f["tarefas"]:
        extra = f" ajustes={t['ajustes']}" if t["ajustes"] else ""
        out.append(f"  [{t['decisao']}] {t['cena']}/{t['agente']} em {t['dispositivo']}{extra}")
        out += [f"      - {m}" for m in t["motivos"]]
    for r in pl.llm:
        if r.get("erro"):
            out.append(f"  LLM ({r.get('papel')}): {r['erro']}" + (" → regras" if r.get("fallback") else ""))
    out += ["", "CONTINUÍSTA — conferirá após a execução: fronteiras (visual/loudness/formato) e os critérios acima.",
            "", "Executando (confirmado)..." if executar else "Nada foi executado."]
    return "\n".join(out)


def cmd_esp_planejar(args) -> int:
    from minivideo_especialistas import pipeline
    ws = Workspace(args.workspace)
    pl = pipeline.planejar(args.pedido, args.entrada, args.orquestrador, ws)
    reg = pipeline.registro(pl, None, {"status": "simulado"})
    path = pipeline.gravar_registro(ws, reg, "plano.json")
    if args.json:
        print(json.dumps(reg, ensure_ascii=False, indent=2))
    else:
        print(_resumo_especialistas(pl))
        print(f"Plano completo (JSON validado): {path}")
    return 0


def cmd_esp_editar(args) -> int:
    from minivideo_especialistas import pipeline
    ws = Workspace(args.workspace)
    pl = pipeline.planejar(args.pedido, args.entrada, args.orquestrador, ws)
    print(_resumo_especialistas(pl, executar=args.confirmar))
    if not args.confirmar:
        print("\nUse --confirmar para executar.")
        return 0
    try:
        res = pipeline.executar(pl, args.saida, ws, permitir_parcial=args.permitir_parcial)
    except pipeline.Recusado as exc:
        print(f"\nRecusado: {exc}", file=sys.stderr)
        return 2
    return _mostrar_resultado(res)


def _mostrar_resultado(res) -> int:
    c = res.get("continuista")
    print()
    if res["status"] != "concluido":
        print(f"Falhou: {res.get('erro')}\nRegistro: {res['registro']}", file=sys.stderr)
        return 1
    print(f"Concluído em {res['segundos']} s · registro: {res['registro']}")
    if c:
        print(f"CONTINUÍSTA — veredito: {c['veredito'].upper()}")
        for k in c["criterios"]:
            print(f"  {'ok ' if k['ok'] else 'NÃO'} {k['id']} {k['tipo']}: alvo {k['alvo']} · medido {k['medido']}")
        for f in c["fronteiras"]:
            print(f"  fronteira {f['entre'][0]}→{f['entre'][1]}: visual={f['diferenca_visual']} "
                  f"loudness={f['salto_loudness_db']} dB · {'ok' if f['ok'] else 'atenção'}")
        for n in c["notas"]:
            print(f"  nota: {n}")
    return 0


def cmd_esp_reproduzir(args) -> int:
    from minivideo_especialistas import pipeline
    ws = Workspace(args.workspace)
    with open(args.registro, encoding="utf-8") as fh:
        reg = json.load(fh)
    try:
        pl = pipeline.plano_de_registro(reg, ws)
    except (pipeline.Recusado, ValueError) as exc:
        print(f"Não é possível reproduzir: {exc}", file=sys.stderr)
        return 2
    saida = args.saida or ws.path("Saidas") + f"/{pl.job_id}.mp4"
    print(_resumo_especialistas(pl, executar=args.confirmar))
    if not args.confirmar:
        print("\nUse --confirmar para executar.")
        return 0
    try:
        res = pipeline.executar(pl, saida, ws, permitir_parcial=True)
    except pipeline.Recusado as exc:
        print(f"Recusado: {exc}", file=sys.stderr)
        return 2
    code = _mostrar_resultado(res)
    antigo = (reg.get("resultado") or {}).get("saida_sha256")
    if code == 0 and antigo:
        igual = antigo == res["saida_sha256"]
        print(f"sha256 da saída {'IGUAL' if igual else 'diferente'} ao job original"
              + ("" if igual else " (codificadores podem variar entre máquinas/versões)"))
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="minivideo-agentes", description="Agentes locais de vídeo do IA-Linux MiniVideo.")
    p.add_argument("--workspace", help="pasta de trabalho (padrão: /data/minivideo ou ~/MiniVideo)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dispositivos", help="CPU, GPUs Vulkan (dGPU/APU) e CUDA").set_defaults(func=cmd_dispositivos)
    s = sub.add_parser("agentes", help="agentes e disponibilidade real")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_agentes)
    s = sub.add_parser("plano", help="explica o plano de um pedido (não executa)")
    s.add_argument("pedido")
    s.set_defaults(func=cmd_plano)
    s = sub.add_parser("executar", help="executa um pedido sobre um vídeo")
    s.add_argument("entrada")
    s.add_argument("pedido")
    s.add_argument("-o", "--saida", required=True)
    s.add_argument("--job-id")
    s.add_argument("--confirmar", action="store_true", help="sem isso, só mostra o plano")
    s.add_argument("--sem-guard", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_executar)

    sub.add_parser("motores", help="matriz de motores: CUDA, Vulkan ou CPU").set_defaults(func=cmd_motores)
    s = sub.add_parser("schemas", help="caminhos dos schemas JSON dos papéis")
    s.add_argument("--exportar", metavar="PASTA")
    s.set_defaults(func=cmd_schemas)

    esp = sub.add_parser("especialistas", help="Diretor, Editor, Fiscal de hardware e Continuísta")
    esub = esp.add_subparsers(dest="esp_cmd", required=True)
    orq = argparse.ArgumentParser(add_help=False)
    orq.add_argument("--orquestrador", choices=("auto", "qwen", "regras"), default="auto",
                     help="auto: Qwen local se configurado, senão regras")
    s = esub.add_parser("planejar", parents=[orq], help="dry-run completo dos quatro papéis (não executa)")
    s.add_argument("pedido")
    s.add_argument("--entrada")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_esp_planejar)
    s = esub.add_parser("editar", parents=[orq], help="planeja, executa e confere um vídeo")
    s.add_argument("entrada")
    s.add_argument("pedido")
    s.add_argument("-o", "--saida", required=True)
    s.add_argument("--confirmar", action="store_true")
    s.add_argument("--permitir-parcial", action="store_true", help="executa mesmo com objetivos rejeitados")
    s.set_defaults(func=cmd_esp_editar)
    s = esub.add_parser("reproduzir", help="reexecuta um job a partir do job.json (sem LLM)")
    s.add_argument("registro")
    s.add_argument("-o", "--saida")
    s.add_argument("--confirmar", action="store_true")
    s.set_defaults(func=cmd_esp_reproduzir)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
