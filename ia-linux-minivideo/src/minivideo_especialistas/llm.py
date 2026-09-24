"""Orquestrador LLM opcional (Qwen3 local via API compatível com OpenAI).

O modelo só devolve TEXTO JSON. Esse texto passa por ``json.loads``, pelo
schema do papel e pela validação semântica; nunca vira comando. Modos:
- ``regras``: nunca chama o modelo;
- ``qwen``: exige o modelo (erro se indisponível ou inválido);
- ``auto``: tenta o modelo e volta às regras em qualquer falha.
Toda chamada (prompts, resposta, erro, tempo) vai para o registro do job.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

from . import schema

ENV_URL = "MINI_IA_VIDEOS_ORCHESTRATOR_URL"
ENV_MODEL = "MINI_IA_VIDEOS_ORCHESTRATOR_MODEL"
ENV_TIMEOUT = "MINI_IA_VIDEOS_ORCHESTRATOR_TIMEOUT"
MODOS = ("regras", "qwen", "auto")


class LLMIndisponivel(RuntimeError):
    pass


class ClienteLLM:
    def __init__(self, url: Optional[str] = None, modelo: Optional[str] = None, timeout: Optional[float] = None):
        self.url = (url or os.environ.get(ENV_URL) or "").rstrip("/")
        self.modelo = modelo or os.environ.get(ENV_MODEL) or "Qwen3-1.7B"
        self.timeout = float(timeout or os.environ.get(ENV_TIMEOUT) or 30)
        if self.url and not self.url.startswith(("http://127.", "http://localhost", "http://[::1]")):
            # Execução local: nenhum serviço externo recebe o pedido do usuário.
            raise LLMIndisponivel(f"URL do orquestrador não é local: {self.url}")

    @property
    def configurado(self) -> bool:
        return bool(self.url)

    def json_por_schema(self, sistema: str, usuario: str, schema_json: Dict) -> Tuple[Dict, Dict]:
        """Devolve (objeto, registro). Não valida semântica: isso é do papel."""
        if not self.configurado:
            raise LLMIndisponivel(f"{ENV_URL} não definido")
        corpo = {
            "model": self.modelo, "temperature": 0, "max_tokens": 2048,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            # llama-server restringe a geração ao schema (gramática); outros servidores podem ignorar.
            "response_format": {"type": "json_schema", "json_schema": {"name": schema_json.get("title", "saida"),
                                                                      "schema": schema_json}},
        }
        reg = {"url": self.url, "modelo": self.modelo, "sistema": sistema, "usuario": usuario,
               "resposta": None, "erro": None, "segundos": None}
        t0 = time.time()
        try:
            req = urllib.request.Request(f"{self.url}/chat/completions", data=json.dumps(corpo).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            texto = data["choices"][0]["message"]["content"]
            reg["resposta"] = texto
            inicio, fim = texto.find("{"), texto.rfind("}")
            if inicio < 0 or fim < inicio:
                raise ValueError("resposta sem objeto JSON")
            obj = json.loads(texto[inicio:fim + 1])
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
            reg["erro"] = f"{type(exc).__name__}: {exc}"
            raise LLMIndisponivel(reg["erro"]) from exc
        finally:
            reg["segundos"] = round(time.time() - t0, 3)
        return obj, reg


def executar_papel(nome: str, modo: str, regras: Callable[[], Dict], validar: Callable[[Dict], Dict],
                   sistema: str, usuario: str, cliente: Optional[ClienteLLM], registros: List[Dict]) -> Dict:
    """Roda um papel no modo pedido, registrando cada tentativa do LLM."""
    if modo not in MODOS:
        raise ValueError(f"modo inválido: {modo}")
    if modo == "regras" or (modo == "auto" and (cliente is None or not cliente.configurado)):
        return regras()
    try:
        if cliente is None:
            raise LLMIndisponivel("nenhum cliente LLM")
        obj, reg = cliente.json_por_schema(sistema, usuario, schema.load(nome))
        reg["papel"] = nome
        registros.append(reg)
        obj["origem"] = "llm"
        try:
            return validar(obj)
        except schema.SchemaError as exc:
            reg["erro"] = f"resposta rejeitada pelo schema/semântica: {exc}"
            raise LLMIndisponivel(reg["erro"]) from exc
    except LLMIndisponivel as exc:
        if not registros or registros[-1].get("papel") != nome:
            registros.append({"papel": nome, "erro": str(exc), "resposta": None})
        if modo == "qwen":
            raise
        registros[-1]["fallback"] = "regras"
        return regras()
