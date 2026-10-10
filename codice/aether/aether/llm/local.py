from typing import Any

from aether.security import local_url


def ensure_local_model(client: Any, base_url: str, model: str) -> dict[str, Any]:
    if not model.strip() or "cloud" in model.lower():
        raise ValueError("Cloud models are disabled")
    response = client.post(f"{local_url(base_url)}/api/show", json={"model": model})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("remote_host") or data.get("remote_model"):
        raise ValueError("Remote Ollama models are disabled")
    return data


def model_digest(client: Any, base_url: str, model: str) -> str | None:
    response = client.get(f"{local_url(base_url)}/api/tags")
    response.raise_for_status()
    data = response.json()
    for item in data.get("models", []):
        names = {item.get("name"), item.get("model")}
        if model in names or (":" not in model and model + ":latest" in names):
            digest = item.get("digest")
            if isinstance(digest, str) and digest.strip():
                return digest
    return None
