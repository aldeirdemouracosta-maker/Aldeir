"""Carregamento e preenchimento de workflows do ComfyUI (formato API).

Os workflows ficam em ``workflows/*.json`` no formato exportado pelo ComfyUI em
"Workflow > Export (API)". Valores dinâmicos usam placeholders:

* ``"{{seed}}"`` — o valor inteiro é substituído mantendo o tipo (int, float, bool);
* ``"video_{{slug}}"`` — placeholders dentro de textos viram texto.

Se um placeholder recebe ``None`` (ex.: imagem final opcional), o nó que o usa é
removido e as ligações de outros nós para ele são apagadas. Assim um mesmo JSON
serve para "só imagem inicial" e "imagem inicial + final".
"""

from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Nome lógico -> arquivo. Para trocar um workflow, substitua o arquivo
# mantendo os mesmos placeholders.
WORKFLOW_FILES = {
    "framepack": "framepack_i2v.json",
    "ltx_t2v": "ltx2_t2v.json",
    "ltx_i2v": "ltx2_i2v.json",
    "ltx_flf": "ltx2_first_last.json",
}

Workflow = dict[str, dict[str, Any]]


class WorkflowError(RuntimeError):
    """Workflow ausente, inválido ou com placeholder sem valor."""


def load_template(workflows_dir: Path, name: str) -> Workflow:
    filename = WORKFLOW_FILES.get(name, f"{name}.json")
    path = workflows_dir / filename
    if not path.exists():
        raise WorkflowError(f"Workflow '{filename}' não encontrado em {workflows_dir}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Workflow '{filename}' tem JSON inválido: {exc}") from exc
    # Chaves começando com "_" são comentários/metadados nossos, não nós.
    nodes = {k: v for k, v in data.items() if not k.startswith("_")}
    if not all(isinstance(v, dict) and "class_type" in v for v in nodes.values()):
        raise WorkflowError(
            f"'{filename}' não está no formato API. No ComfyUI use 'Export (API)'."
        )
    return nodes


def find_placeholders(workflow: Workflow) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            found.update(PLACEHOLDER.findall(value))
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)

    walk(workflow)
    return found


def _substitute(value: Any, params: dict[str, Any]) -> Any:
    if isinstance(value, str):
        full = PLACEHOLDER.fullmatch(value.strip())
        if full:
            return params[full.group(1)]
        return PLACEHOLDER.sub(lambda m: str(params[m.group(1)]), value)
    if isinstance(value, list):
        return [_substitute(v, params) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, params) for k, v in value.items()}
    return value


def _is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


def prune_nodes(workflow: Workflow, node_ids: set[str]) -> Workflow:
    """Remove nós e, em cascata, entradas que apontam para eles.

    Nós cuja entrada removida era a única fonte de dados também são removidos
    se marcados com ``"_optional": true`` (útil para cadeias opcionais inteiras).
    """
    wf = {k: v for k, v in workflow.items() if k not in node_ids}
    changed = True
    while changed:
        changed = False
        for node_id, node in list(wf.items()):
            inputs = node.get("inputs", {})
            dangling = [k for k, v in inputs.items() if _is_link(v) and v[0] not in wf]
            if not dangling:
                continue
            if node.get("_optional"):
                del wf[node_id]
            else:
                for key in dangling:
                    del inputs[key]
            changed = True
    return wf


def build_workflow(template: Workflow, params: dict[str, Any]) -> Workflow:
    """Preenche placeholders e remove nós opcionais cujo valor é ``None``."""
    missing = find_placeholders(template) - params.keys()
    if missing:
        raise WorkflowError(f"Faltam valores para: {', '.join(sorted(missing))}")
    wf = copy.deepcopy(template)
    disabled = {
        node_id for node_id, node in wf.items()
        if any(params[name] is None for name in find_placeholders(node.get("inputs", {})))
    }
    wf = prune_nodes(wf, disabled)
    filled = {k: _substitute(v, params) for k, v in wf.items()}
    # Remove nossa marcação interna antes de enviar ao ComfyUI.
    for node in filled.values():
        node.pop("_optional", None)
    return filled


def missing_node_types(workflow: Workflow, object_info: dict[str, Any]) -> list[str]:
    """Tipos de nós usados no workflow que não estão instalados no ComfyUI."""
    return sorted({n["class_type"] for n in workflow.values()} - object_info.keys())


def describe_validation(workflows_dir: Path, object_info: dict[str, Any] | None) -> str:
    """Relatório em Markdown sobre todos os workflows (usado na aba Sistema)."""
    lines = []
    for name, filename in WORKFLOW_FILES.items():
        try:
            wf = load_template(workflows_dir, name)
        except WorkflowError as exc:
            lines.append(f"- ❌ **{name}**: {exc}")
            continue
        if object_info is None:
            lines.append(f"- 🔘 **{name}** (`{filename}`): {len(wf)} nós — ComfyUI offline, não validado")
            continue
        missing = missing_node_types(wf, object_info)
        if missing:
            lines.append(f"- ⚠️ **{name}**: nós ausentes no ComfyUI: `{', '.join(missing)}`")
        else:
            lines.append(f"- ✅ **{name}** (`{filename}`): todos os {len(wf)} nós disponíveis")
    return "\n".join(lines)
