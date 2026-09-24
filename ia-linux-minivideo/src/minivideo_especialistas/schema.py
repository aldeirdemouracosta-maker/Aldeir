"""Validador de JSON Schema (subconjunto do draft 2020-12), sem dependências.

Suporta: type, properties, required, additionalProperties (bool), enum,
const, minimum, maximum, minLength, maxLength, pattern, items, minItems,
maxItems, anyOf e $ref local ("#/$defs/..."). É o que os schemas dos
papéis usam; qualquer palavra-chave fora disso é recusada ao carregar o
schema, para não haver validação "silenciosamente frouxa".
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

SUPPORTED = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "properties", "required",
    "additionalProperties", "enum", "const", "minimum", "maximum", "minLength", "maxLength",
    "pattern", "items", "minItems", "maxItems", "anyOf", "default",
}
TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
    "integer": int, "number": (int, float),
}
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")


class SchemaError(ValueError):
    """JSON não obedece ao schema. ``erros`` lista cada caminho e motivo."""

    def __init__(self, erros: List[str]):
        super().__init__("; ".join(erros[:8]) + (" …" if len(erros) > 8 else ""))
        self.erros = erros


def _check_keywords(schema: Any, path: str = "#") -> None:
    if isinstance(schema, dict):
        unknown = set(schema) - SUPPORTED
        if unknown:
            raise ValueError(f"schema usa palavras-chave não suportadas em {path}: {sorted(unknown)}")
        for k, v in schema.items():
            if k in ("properties", "$defs"):
                for name, sub in v.items():
                    _check_keywords(sub, f"{path}/{k}/{name}")
            elif k in ("items",):
                _check_keywords(v, f"{path}/{k}")
            elif k == "anyOf":
                for i, sub in enumerate(v):
                    _check_keywords(sub, f"{path}/anyOf/{i}")


def _type_ok(value: Any, typ: str) -> bool:
    if typ in ("integer", "number") and isinstance(value, bool):
        return False
    if typ == "integer" and isinstance(value, float):
        return value.is_integer()
    return isinstance(value, TYPES[typ])


def _validate(value: Any, schema: Dict, root: Dict, path: str, erros: List[str]) -> None:
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            erros.append(f"{path}: $ref não suportado {ref}")
            return
        schema = root["$defs"][ref.split("/")[-1]]
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            tmp: List[str] = []
            _validate(value, sub, root, path, tmp)
            if not tmp:
                break
        else:
            erros.append(f"{path}: não corresponde a nenhuma alternativa permitida")
            return
    typ = schema.get("type")
    if typ is not None:
        types = typ if isinstance(typ, list) else [typ]
        if not any(_type_ok(value, t) for t in types):
            erros.append(f"{path}: tipo {type(value).__name__}, esperado {typ}")
            return
    if "const" in schema and value != schema["const"]:
        erros.append(f"{path}: deve ser {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        erros.append(f"{path}: {value!r} fora de {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            erros.append(f"{path}: {value} < mínimo {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            erros.append(f"{path}: {value} > máximo {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            erros.append(f"{path}: texto curto demais")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            erros.append(f"{path}: texto longo demais (máx. {schema['maxLength']})")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            erros.append(f"{path}: {value!r} não segue o padrão {schema['pattern']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            erros.append(f"{path}: mínimo {schema['minItems']} itens")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            erros.append(f"{path}: máximo {schema['maxItems']} itens")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], root, f"{path}/{i}", erros)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                erros.append(f"{path}: falta o campo obrigatório '{req}'")
        if schema.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    erros.append(f"{path}: campo não permitido '{k}'")
        for k, sub in props.items():
            if k in value:
                _validate(value[k], sub, root, f"{path}/{k}", erros)


def validate(value: Any, schema: Dict) -> None:
    erros: List[str] = []
    _validate(value, schema, schema, "#", erros)
    if erros:
        raise SchemaError(erros)


_CACHE: Dict[str, Dict] = {}


def load(name: str) -> Dict:
    """Carrega ``schemas/<name>.schema.json`` e confere as palavras-chave usadas."""
    if name not in _CACHE:
        with open(os.path.join(SCHEMA_DIR, f"{name}.schema.json"), encoding="utf-8") as fh:
            schema = json.load(fh)
        _check_keywords(schema)
        _CACHE[name] = schema
    return _CACHE[name]


def check(name: str, value: Any) -> Any:
    validate(value, load(name))
    return value
