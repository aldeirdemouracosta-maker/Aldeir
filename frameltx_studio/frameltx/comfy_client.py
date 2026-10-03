"""Cliente da API do ComfyUI (HTTP + WebSocket).

Fluxo de uma execução:
1. ``upload_image`` envia as imagens de entrada para ``/upload/image``;
2. ``queue_prompt`` envia o workflow para ``/prompt``;
3. ``wait_for_prompt`` escuta o WebSocket ``/ws`` repassando progresso e
   previews (frames parciais) para um callback;
4. ``download_outputs`` baixa os arquivos gerados via ``/history`` e ``/view``.
"""

from __future__ import annotations

import io
import json
import logging
import struct
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websocket
from PIL import Image

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".gif", ".webp"}


class ComfyError(RuntimeError):
    """Erro de comunicação ou execução no ComfyUI, com mensagem amigável."""


class ComfyOOMError(ComfyError):
    """O ComfyUI ficou sem memória de vídeo (CUDA out of memory)."""


@dataclass
class ComfyProgress:
    """Evento de progresso vindo do ComfyUI."""

    fraction: float  # 0..1 dentro da execução atual
    message: str
    preview: Image.Image | None = None


ProgressCallback = Callable[[ComfyProgress], None]

OOM_MARKERS = ("out of memory", "outofmemory", "cuda error: out of memory", "allocation on device")


def _friendly_execution_error(data: dict[str, Any]) -> ComfyError:
    node = data.get("node_type", "?")
    msg = str(data.get("exception_message", "")).strip()
    if any(m in msg.lower() for m in OOM_MARKERS) or "OutOfMemory" in str(data.get("exception_type")):
        return ComfyOOMError(f"VRAM insuficiente no nó {node}.")
    return ComfyError(f"Erro no nó '{node}': {msg.splitlines()[0] if msg else 'erro desconhecido'}")


def _friendly_validation_error(body: dict[str, Any]) -> str:
    """Resume a resposta 400 do /prompt (modelos ausentes, nós desconhecidos...)."""
    parts = []
    err = body.get("error", {})
    if err:
        parts.append(err.get("message", "workflow inválido"))
    for node_id, info in body.get("node_errors", {}).items():
        for e in info.get("errors", []):
            detail = e.get("details") or e.get("message", "")
            parts.append(f"nó {node_id} ({info.get('class_type', '?')}): {detail}")
    text = "; ".join(parts) or "workflow rejeitado"
    if "not in list" in text or "value_not_in_list" in json.dumps(body):
        text += " — verifique se os modelos estão nas pastas do ComfyUI e os nomes no config.json."
    return text


class ComfyClient:
    def __init__(self, base_url: str, timeout: int = 3600) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    # ---------- HTTP ----------
    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        try:
            resp = requests.get(f"{self.base_url}{path}", timeout=kwargs.pop("timeout", 30), **kwargs)
            resp.raise_for_status()
            return resp
        except requests.ConnectionError as exc:
            raise ComfyError(
                f"Não foi possível conectar ao ComfyUI em {self.base_url}. Ele está aberto?"
            ) from exc
        except requests.RequestException as exc:
            raise ComfyError(f"Falha na requisição {path}: {exc}") from exc

    def is_online(self) -> bool:
        try:
            self._get("/system_stats", timeout=3)
            return True
        except ComfyError:
            return False

    def object_info(self) -> dict[str, Any]:
        return self._get("/object_info", timeout=60).json()

    def free_memory(self) -> None:
        """Pede ao ComfyUI para descarregar modelos e liberar VRAM."""
        try:
            requests.post(f"{self.base_url}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
        except requests.RequestException:
            log.debug("Endpoint /free indisponível")

    def interrupt(self) -> None:
        try:
            requests.post(f"{self.base_url}/interrupt", timeout=5)
        except requests.RequestException:
            pass

    def upload_image(self, path: Path) -> str:
        """Envia uma imagem e retorna o nome a ser usado no nó LoadImage."""
        try:
            with path.open("rb") as fh:
                resp = requests.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (path.name, fh, "image/png")},
                    data={"overwrite": "true", "type": "input"},
                    timeout=60,
                )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ComfyError(f"Falha ao enviar imagem {path.name}: {exc}") from exc
        info = resp.json()
        sub = info.get("subfolder", "")
        return f"{sub}/{info['name']}" if sub else info["name"]

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id},
                timeout=30,
            )
        except requests.ConnectionError as exc:
            raise ComfyError(f"ComfyUI offline em {self.base_url}.") from exc
        if resp.status_code == 400:
            raise ComfyError("Workflow rejeitado pelo ComfyUI: " + _friendly_validation_error(resp.json()))
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]
        log.info("Workflow enfileirado no ComfyUI: %s", prompt_id)
        return prompt_id

    # ---------- WebSocket ----------
    def _ws_url(self) -> str:
        scheme = "wss" if self.base_url.startswith("https") else "ws"
        host = self.base_url.split("://", 1)[-1]
        return f"{scheme}://{host}/ws?clientId={self.client_id}"

    def open_ws(self) -> websocket.WebSocket:
        try:
            return websocket.create_connection(self._ws_url(), timeout=30)
        except (OSError, websocket.WebSocketException) as exc:
            raise ComfyError(f"Não foi possível abrir o WebSocket do ComfyUI: {exc}") from exc

    @staticmethod
    def _decode_preview(payload: bytes) -> Image.Image | None:
        """Mensagens binárias: [tipo:u32][formato:u32][imagem]. Tipo 1 = preview."""
        if len(payload) < 8:
            return None
        event_type, _fmt = struct.unpack(">II", payload[:8])
        if event_type != 1:
            return None
        try:
            return Image.open(io.BytesIO(payload[8:])).convert("RGB")
        except OSError:
            return None

    def wait_for_prompt(
        self, ws: websocket.WebSocket, prompt_id: str, on_progress: ProgressCallback | None = None,
        workflow: dict[str, Any] | None = None,
    ) -> None:
        """Bloqueia até o prompt terminar, repassando progresso. Lança ComfyError em falhas."""
        notify = on_progress or (lambda _p: None)
        total_nodes = max(len(workflow or {}), 1)
        done_nodes: set[str] = set()
        current_node = ""
        deadline = time.monotonic() + self.timeout
        ws.settimeout(15)

        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except (OSError, websocket.WebSocketException) as exc:
                raise ComfyError(f"Conexão com o ComfyUI perdida: {exc}") from exc

            if isinstance(raw, bytes):
                if preview := self._decode_preview(raw):
                    notify(ComfyProgress(len(done_nodes) / total_nodes, "Gerando frames…", preview))
                continue

            msg = json.loads(raw)
            mtype, data = msg.get("type"), msg.get("data", {})
            if data.get("prompt_id") not in (None, prompt_id):
                continue  # evento de outro prompt

            if mtype == "executing":
                if data.get("node") is None:
                    return  # fim da execução
                if current_node:
                    done_nodes.add(current_node)
                current_node = data["node"]
                node_type = (workflow or {}).get(current_node, {}).get("class_type", current_node)
                notify(ComfyProgress(len(done_nodes) / total_nodes, f"Executando {node_type}"))
            elif mtype == "execution_cached":
                done_nodes.update(data.get("nodes", []))
            elif mtype == "progress":
                step, maxv = data.get("value", 0), max(data.get("max", 1), 1)
                # Progresso do sampler domina o tempo: mapeia para o intervalo do nó atual.
                base = len(done_nodes) / total_nodes
                frac = base + (step / maxv) * (1 / total_nodes)
                notify(ComfyProgress(min(frac, 0.99), f"Passo {step}/{maxv}"))
            elif mtype == "execution_error":
                raise _friendly_execution_error(data)
            elif mtype == "execution_interrupted":
                raise ComfyError("Geração interrompida.")
            elif mtype == "execution_success":
                return
        raise ComfyError(f"Tempo limite de {self.timeout}s excedido aguardando o ComfyUI.")

    # ---------- Saídas ----------
    def download_outputs(self, prompt_id: str, out_dir: Path) -> list[Path]:
        """Baixa todos os arquivos gerados (vídeos primeiro)."""
        history = self._get(f"/history/{prompt_id}").json().get(prompt_id, {})
        status = history.get("status", {})
        if status.get("status_str") == "error":
            for kind, data in status.get("messages", []):
                if kind == "execution_error":
                    raise _friendly_execution_error(data)
            raise ComfyError("O ComfyUI reportou erro na execução.")

        out_dir.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        for node_output in history.get("outputs", {}).values():
            for items in node_output.values():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and "filename" in item and item.get("type") != "temp":
                        files.append(self._download_file(item, out_dir))
        files.sort(key=lambda p: p.suffix.lower() not in VIDEO_EXTS)
        if not files:
            raise ComfyError("O workflow terminou mas não gerou nenhum arquivo de saída.")
        return files

    def _download_file(self, item: dict[str, Any], out_dir: Path) -> Path:
        params = {"filename": item["filename"], "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")}
        resp = self._get("/view", params=params, timeout=300)
        target = out_dir / Path(item["filename"]).name
        target.write_bytes(resp.content)
        return target

    # ---------- Execução completa ----------
    def run(
        self, workflow: dict[str, Any], out_dir: Path, on_progress: ProgressCallback | None = None,
    ) -> list[Path]:
        """Enfileira, acompanha e baixa o resultado de um workflow."""
        ws = self.open_ws()  # abre antes de enfileirar para não perder eventos
        try:
            prompt_id = self.queue_prompt(workflow)
            self.wait_for_prompt(ws, prompt_id, on_progress, workflow)
        finally:
            ws.close()
        return self.download_outputs(prompt_id, out_dir)
