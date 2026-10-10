from urllib.parse import urlsplit


def local_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment:
        raise ValueError("Ollama exige endpoint HTTP de loopback local")
    return value.rstrip("/")

