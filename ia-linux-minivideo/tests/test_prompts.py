"""Assistente de prompts: diálogo por regras, LLM local simulado, formatos por modelo."""

import http.server
import json
import threading

import pytest

from minivideo_especialistas.llm import ClienteLLM, LLMIndisponivel
from minivideo_prompts import cli, modelos
from minivideo_prompts.conversa import Conversa, salvar, separar


def conversar(c, falas):
    c.abrir()
    for f in falas:
        ultima = c.responder(f)
    return ultima


def test_separa_quem_faz_o_que_e_onde():
    assert separar("um cachorro caramelo correndo na praia") == {
        "assunto": "um cachorro caramelo", "acao": "correndo", "cenario": "na praia"}
    assert separar("uma xícara de café") == {"assunto": "uma xícara de café"}


def test_dialogo_por_regras_preenche_a_ficha_e_monta_o_prompt():
    c = Conversa()
    conversar(c, ["um cachorro correndo na praia ao pôr do sol", "1", "drone", "2", "3", "acompanha",
                  "quente", "vertical", "6", "pessoas"])
    f = c.ficha
    assert f["assunto"] == "um cachorro" and f["periodo"] == "pôr do sol"
    assert f["angulo"] == "aéreo (drone)" and f["movimento"] == "acompanha (travelling)"
    assert f["orientacao"] == "vertical 9:16" and f["duracao_s"] == "6" and f["evitar"] == "pessoas"
    assert c.pendente is None  # terminou: nada mais a perguntar
    doc = c.resultado()
    assert doc["origem"] == "regras" and doc["formato"] == "minivideo-prompt/1"
    assert doc["prompt"].startswith("photorealistic")
    assert "aerial drone shot" in doc["prompt"] and "golden hour" in doc["prompt"]
    assert doc["prompt_negativo"].startswith("pessoas, ")
    assert doc["parametros"] == {"tamanho": "704*1280", "fps": 24, "quadros": 145, "duracao_s": 6.0}
    assert [d["papel"] for d in doc["dialogo"][:2]] == ["assistente", "usuario"]


def test_resposta_fora_da_pergunta_e_aproveitada():
    c = Conversa()
    conversar(c, ["um gato dormindo no sofá"])
    assert c.pendente == "estilo"
    r = c.responder("drone")
    assert "Anotei angulo" in r and c.ficha["angulo"] == "aéreo (drone)" and c.pendente == "estilo"
    assert "Não entendi" in c.responder("xyz")


def test_pronto_antecipado_so_com_o_essencial():
    c = Conversa()
    c.abrir()
    assert "falta o essencial" in c.responder("/pronto")
    conversar(c, ["um farol piscando numa ilha"])
    assert "Pronto" in c.responder("/pronto")
    assert c.resultado()["parametros"]["duracao_s"] == 5.0


def test_formatos_por_modelo():
    ficha = {"assunto": "um barco", "acao": "navegando", "cenario": "no mar", "plano": "plano aberto",
             "duracao_s": "5"}
    wan = modelos.montar(ficha, "wan2.2-ti2v-5b")
    assert (wan["parametros"]["quadros"] - 1) % 4 == 0 and wan["parametros"]["fps"] == 24
    vace = modelos.montar(ficha, "wan2.1-vace-1.3b")
    assert vace["parametros"]["tamanho"] == "832*480" and vace["parametros"]["quadros"] == 81
    ltx = modelos.montar(ficha, "ltx-2.3")
    assert (ltx["parametros"]["quadros"] - 1) % 8 == 0
    assert ltx["prompt"].startswith("um barco navegando") and "Camera: wide shot" in ltx["prompt"]
    with pytest.raises(ValueError):
        modelos.montar(ficha, "sora")


def test_salvar_em_projetos(tmp_path):
    c = Conversa("ltx-2.3")
    conversar(c, ["uma bailarina girando num palco", "/pronto"])
    caminho = salvar(c.resultado(), str(tmp_path / "Projetos" / "demo"))
    assert caminho.endswith("-ltx-2.3.json")
    assert json.load(open(caminho))["ficha"]["assunto"] == "uma bailarina"


class LLMFalso:
    """Servidor no formato OpenAI (como o llama-server) com respostas programadas."""

    def __init__(self, respostas):
        self.respostas, self.pedidos = list(respostas), []
        dono = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                dono.pedidos.append(corpo)
                conteudo = dono.respostas.pop(0) if dono.respostas else "{}"
                dados = json.dumps({"choices": [{"message": {"content": conteudo}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


def test_llm_entende_frase_livre_e_rotulo_invalido_e_descartado():
    llm = LLMFalso([json.dumps({"ficha": {"assunto": "uma senhora", "acao": "regando flores",
                                          "cenario": "num jardim", "periodo": "manhãzinha",
                                          "angulo": "de cima"},
                                "pergunta": "Qual o estilo do vídeo?"}),
                    json.dumps({"prompt": "An elderly woman waters flowers in a sunny garden, high-angle shot."})])
    c = Conversa(cliente=ClienteLLM(url=llm.url), modo="auto")
    c.abrir()
    r = c.responder("quero minha avó regando as flores do jardim, filmada de cima")
    assert r == "Qual o estilo do vídeo?"
    assert c.ficha["assunto"] == "uma senhora" and c.ficha["angulo"] == "de cima"
    assert c.ficha.get("periodo") in (None, "dia")  # "manhãzinha" não é rótulo; só entra se casar
    assert llm.pedidos[0]["response_format"]["type"] == "json_schema"
    doc = c.resultado(refinar=True)
    assert doc["origem"] == "llm" and doc["prompt"].startswith("An elderly woman")
    assert [r["papel"] for r in doc["llm"]] == ["conversa", "refino"]
    llm.httpd.shutdown()


def test_llm_com_resposta_invalida_volta_para_regras():
    llm = LLMFalso(["isto não é JSON", json.dumps({"ficha": {"comando": "rm -rf /"}, "pergunta": "x"})])
    c = Conversa(cliente=ClienteLLM(url=llm.url), modo="auto")
    c.abrir()
    c.responder("um trem passando numa ponte")
    assert c.ficha["assunto"] == "um trem" and c.pendente == "estilo"
    c.responder("1")  # schema recusa a chave "comando": regras de novo
    assert c.ficha["estilo"] == "realista (cinema)" and "comando" not in c.ficha
    assert all(r.get("fallback") == "regras" or r.get("erro") for r in c.registros)
    llm.httpd.shutdown()


def test_modo_qwen_sem_servidor_falha_e_refino_exige_llm():
    c = Conversa(modo="qwen", cliente=ClienteLLM(url="http://127.0.0.1:9/v1", timeout=1))
    c.abrir()
    with pytest.raises(LLMIndisponivel):
        c.responder("um carro na chuva")
    c2 = Conversa()
    conversar(c2, ["um carro andando na chuva", "/pronto"])
    with pytest.raises(LLMIndisponivel):
        c2.resultado(refinar=True)


def test_cli_conversar_e_gerar(tmp_path, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("um navio chegando no porto\n/pronto\n"))
    assert cli.main(["conversar", "--modo", "regras", "--salvar", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert '"modelo": "wan2.2-ti2v-5b"' in out and "salvo:" in out
    ficha = tmp_path / "ficha.json"
    ficha.write_text(json.dumps({"assunto": "um navio", "acao": "chegando", "cenario": "no porto"}))
    assert cli.main(["gerar", str(ficha), "--modelo", "ltx-2.3"]) == 0
    assert "um navio chegando" in capsys.readouterr().out


def test_schemas_do_assistente_usam_so_palavras_suportadas():
    from minivideo_especialistas import schema
    from minivideo_prompts.conversa import SCHEMAS
    for n in ("conversa", "refino", "prompt"):
        assert schema.load(n, SCHEMAS)["title"] == n


def test_servidor_local_sobe_so_em_localhost_e_para(tmp_path, monkeypatch):
    import os
    import sys
    from minivideo_prompts.servidor import ServidorLocal, achar_gguf
    llm = tmp_path / "Modelos" / "llm"
    llm.mkdir(parents=True)
    (llm / "grande.gguf").write_bytes(b"GGUF" + b"0" * 2000)
    (llm / "pequeno.gguf").write_bytes(b"GGUF" + b"0" * 10)
    assert achar_gguf(str(tmp_path / "Modelos")).endswith("pequeno.gguf")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    falso = bindir / "llama-server"
    falso.write_text(f"""#!{sys.executable}
import http.server, json, sys
a = sys.argv
assert a[a.index("--host") + 1] == "127.0.0.1"
porta = int(a[a.index("--port") + 1])
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        corpo = json.dumps({{"status": "ok"}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(corpo))); self.end_headers()
        self.wfile.write(corpo)
    def log_message(self, *x): pass
http.server.HTTPServer(("127.0.0.1", porta), H).serve_forever()
""")
    falso.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    import socket
    with socket.socket() as s_:
        s_.bind(("127.0.0.1", 0))
        porta = s_.getsockname()[1]
    srv = ServidorLocal(str(llm / "pequeno.gguf"), porta=porta)
    srv.iniciar(str(tmp_path / "llama.log"), espera_s=20)
    try:
        assert srv.url == f"http://127.0.0.1:{porta}/v1" and srv.proc.poll() is None
        assert ClienteLLM(url=srv.url).configurado
    finally:
        srv.parar()
    assert srv.proc is None
