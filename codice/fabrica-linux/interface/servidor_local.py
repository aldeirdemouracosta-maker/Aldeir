"""Consulta explícita de modelos: nenhum ID é presumido."""
import json
import urllib.request
from urllib.parse import urlsplit


def consultar_modelos(url):
    partes = urlsplit(url)
    if partes.scheme != 'http' or partes.hostname not in ('localhost', '127.0.0.1', '::1') or partes.username or partes.password:
        raise ValueError('Informe um servidor HTTP local, sem credenciais.')
    if partes.query or partes.fragment or partes.path.rstrip('/') not in ('', '/v1'):
        raise ValueError('O endereço deve terminar na raiz ou em /v1.')
    base = url.rstrip('/')
    if not base.endswith('/v1'):
        base += '/v1'
    with urllib.request.urlopen(base + '/models', timeout=5) as resposta:
        dados = json.load(resposta)
    modelos = sorted({m['id'] for m in dados['data'] if isinstance(m.get('id'), str)})
    if not modelos:
        raise ValueError('O servidor não possui modelos disponíveis.')
    return base, modelos
