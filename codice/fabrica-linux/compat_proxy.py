"""Adaptador da API de ferramentas desta base para o núcleo corrigido do proxy."""
from fabrica_correcoes import fabrica_proxy as core

NOMES = {"escrever_arquivo": "write_file", "ler_arquivo": "read_file",
         "executar_comando": "run_command"}


def normalizar(nome, args):
    args = dict(args)
    for origem, destino in (("caminho", "path"), ("conteudo", "content"), ("comando", "command")):
        if origem in args:
            args[destino] = args.pop(origem)
    return NOMES.get(nome, nome), args


def resultado_normalizado(nome, resultado):
    import json
    if nome == "escrever_arquivo":
        return {"success": resultado == "ok"}
    if nome == "executar_comando":
        try:
            dado = json.loads(resultado)
            return {"exit_code": dado["codigo_saida"], "stdout": dado.get("stdout"),
                    "stderr": dado.get("stderr"), "timed_out": dado.get("expirou")}
        except (ValueError, KeyError, TypeError):
            pass
    return resultado


def repeticao_sem_progresso(historico, nome, args):
    adaptado = [(*normalizar(n, a), resultado_normalizado(n, r)) for n, a, r in historico]
    n, a = normalizar(nome, args)
    anteriores = core.loop_outcomes(adaptado).get(core.signature(n, a), [])
    return len(anteriores) >= 2 and anteriores[-1] == anteriores[-2]


def extrair(texto, nomes):
    chamadas = core.extract_text_tool_calls(texto, nomes)
    if len(chamadas) != 1:
        return None
    import json
    fn = chamadas[0]["function"]
    return {"name": fn["name"], "arguments": json.loads(fn["arguments"])}


def afirma_sem_confirmacao(texto, historico):
    adaptado = [(*normalizar(n, a), resultado_normalizado(n, r)) for n, a, r in historico]
    return core.claims_work(texto) and not core.confirmed_claim(texto, adaptado)
