"""Testes do proxy com um servidor falso que imita o Ollama.  Rode:  python3 -m unittest -v"""
import json
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fabrica_proxy as fp

TOOLS = [{"type": "function", "function": {"name": n, "parameters": {}}}
         for n in ("list_dir", "read_file", "write_file", "run_command")]
SCRIPT = {}   # palavra-chave na última mensagem -> lista de respostas (uma por chamada)


def reply(content="", calls=None):
    return {"content": content, "tool_calls": calls or []}


def call(name, args):
    return {"id": "c_" + name, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        out = b'{"data":[{"id":"qwen3:8b"}]}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.last_body = b
        text = json.dumps(b["messages"], ensure_ascii=False)
        key = next((k for k in SCRIPT if k in text), None)
        r = SCRIPT[key].pop(0) if key and SCRIPT[key] else reply("ok")
        if r == "ERRO":
            self.send_response(404)
            out = b'{"error":{"message":"model \\"x\\" not found"}}'
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def send(d, fin=None):
            c = {"id": "x", "created": 1, "model": "m",
                 "choices": [{"index": 0, "delta": d, "finish_reason": fin}]}
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
            self.wfile.flush()
        send({"reasoning": "pensando"})
        for k in range(0, len(r["content"]), 5):
            send({"content": r["content"][k:k + 5]})
        for i, tc in enumerate(r["tool_calls"]):
            a = tc["function"]["arguments"]
            send({"tool_calls": [{"index": i, "id": tc["id"], "type": "function",
                                  "function": {"name": tc["function"]["name"], "arguments": a[:4]}}]})
            send({"tool_calls": [{"index": i, "function": {"arguments": a[4:]}}]})
        send({}, "tool_calls" if r["tool_calls"] else "stop")
        self.wfile.write(b'data: {"id":"x","choices":[],"usage":{"total_tokens":7}}\n\ndata: [DONE]\n\n')


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = serve(FakeOllama)
        fp.CONFIG["upstream"] = "http://127.0.0.1:%d" % cls.ollama.server_port
        fp.log = lambda msg: None
        cls.proxy = serve(fp.Handler)
        cls.url = "http://127.0.0.1:%d/v1/chat/completions" % cls.proxy.server_port

    def setUp(self):
        SCRIPT.clear()
        fp.CONFIG.update(no_think=False, keepalive=10)

    def post(self, messages, stream=False):
        body = {"model": "qwen3:8b", "messages": messages, "tools": TOOLS, "stream": stream}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
        if not stream:
            return json.loads(raw)["choices"][0]
        chunks = [json.loads(l[6:]) for l in raw.splitlines() if l.startswith("data: {")]
        self.assertIn("data: [DONE]", raw)
        return {"message": chunks[0]["choices"][0]["delta"],
                "finish_reason": chunks[1]["choices"][0]["finish_reason"], "raw": raw}

    # 1 ---------------------------------------------------------------
    def test_ferramenta_em_texto_vira_tool_call(self):
        SCRIPT["K1"] = [reply('{"name": "write_file", "arguments": {"path": "a.py", "content": "x"}}')]
        c = self.post([{"role": "user", "content": "K1 crie a.py"}])
        self.assertEqual(c["message"]["tool_calls"][0]["function"]["name"], "write_file")
        self.assertEqual(c["finish_reason"], "tool_calls")

    def test_ferramenta_em_texto_com_cercas_markdown(self):
        SCRIPT["K1b"] = [reply('```json\n{"name": "run_command", "arguments": {"cmd": "ls"}}\n```')]
        c = self.post([{"role": "user", "content": "K1b rode ls"}], stream=True)
        self.assertEqual(c["message"]["tool_calls"][0]["function"]["name"], "run_command")

    def test_exemplo_json_no_meio_de_explicacao_nao_executa(self):
        long_text = "Explicação detalhada. " * 30
        SCRIPT["K1c"] = [reply(long_text + '{"name": "write_file", "arguments": {"path": "a"}}' + long_text)]
        c = self.post([{"role": "user", "content": "K1c como funciona o write_file?"}])
        self.assertFalse(c["message"].get("tool_calls"))

    def test_tool_calls_nativas_em_pedacos_sao_remontadas(self):
        SCRIPT["K1d"] = [reply("", [call("write_file", {"path": "a.py", "content": "print(1)"})])]
        c = self.post([{"role": "user", "content": "K1d crie a.py"}])
        args = json.loads(c["message"]["tool_calls"][0]["function"]["arguments"])
        self.assertEqual(args, {"path": "a.py", "content": "print(1)"})

    # 2 ---------------------------------------------------------------
    def test_mentira_e_cobrada_e_ia_passa_a_usar_ferramenta(self):
        SCRIPT["K2"] = [reply("✓ Arquivo calc.py criado."),
                        reply("", [call("write_file", {"path": "calc.py", "content": "x"})])]
        c = self.post([{"role": "user", "content": "K2 crie calc.py"}])
        self.assertEqual(c["message"]["tool_calls"][0]["function"]["name"], "write_file")

    def test_mentira_insistente_vira_aviso(self):
        SCRIPT["K3"] = [reply("✓ calc.py criado.")] * 3
        c = self.post([{"role": "user", "content": "K3 crie calc.py"}])
        self.assertIn("⚠️ [proxy]", c["message"]["content"])

    def test_pergunta_sem_acao_nao_e_cobrada(self):
        SCRIPT["K4"] = [reply("A função somar foi criada em calc.py para somar números.")]
        c = self.post([{"role": "user", "content": "K4 o que tem em calc.py?"}])
        self.assertNotIn("[proxy]", c["message"]["content"])
        self.assertEqual(SCRIPT["K4"], [])   # só uma chamada ao modelo

    def test_versao_nao_conta_como_arquivo(self):
        self.assertFalse(fp.claims_work("✓ Atualizado para a versão 3.12"))
        self.assertTrue(fp.claims_work("✓ Arquivo test_calc.py criado"))

    def test_resumo_depois_de_escrever_de_verdade_nao_e_cobrado(self):
        SCRIPT["K5"] = [reply("✓ calc.py criado.")]
        msgs = [{"role": "user", "content": "K5 crie calc.py"},
                {"role": "assistant", "content": "", "tool_calls": [call("write_file", {"path": "calc.py"})]},
                {"role": "tool", "tool_call_id": "c_write_file", "content": "ok"}]
        c = self.post(msgs)
        self.assertEqual(c["message"]["content"], "✓ calc.py criado.")

    # 3 ---------------------------------------------------------------
    def _history(self, results):
        msgs = [{"role": "user", "content": "K6 rode os testes"}]
        for i, res in enumerate(results):
            msgs.append({"role": "assistant", "content": "", "tool_calls": [
                dict(call("run_command", {"cmd": "python3 -m unittest"}), id="t%d" % i)]})
            msgs.append({"role": "tool", "tool_call_id": "t%d" % i, "content": res})
        return msgs

    def test_loop_com_mesmo_resultado_e_interrompido(self):
        SCRIPT["K6"] = [reply("", [call("run_command", {"cmd": "python3 -m unittest"})])]
        c = self.post(self._history(["FAILED x", "FAILED x"]))
        self.assertIn("⛔", c["message"]["content"])
        self.assertFalse(c["message"].get("tool_calls"))

    def test_repetir_teste_com_resultados_diferentes_e_permitido(self):
        SCRIPT["K6"] = [reply("", [call("run_command", {"cmd": "python3 -m unittest"})])]
        c = self.post(self._history(["FAILED a", "FAILED b"]))
        self.assertTrue(c["message"].get("tool_calls"))

    # 4 ---------------------------------------------------------------
    def test_erro_http_do_servidor_aparece_na_tela(self):
        SCRIPT["K7"] = ["ERRO"]
        c = self.post([{"role": "user", "content": "K7 oi"}])
        self.assertIn("not found", c["message"]["content"])

    def test_sinal_de_vida_durante_espera(self):
        fp.CONFIG["keepalive"] = 0.2
        orig = fp.call_upstream
        fp.call_upstream = lambda body: (time.sleep(0.7), orig(body))[1]
        try:
            c = self.post([{"role": "user", "content": "K8 oi"}], stream=True)
        finally:
            fp.call_upstream = orig
        self.assertIn(": aguardando o modelo", c["raw"])

    def test_think_no_texto_vai_para_reasoning(self):
        SCRIPT["K9"] = [reply("<think>hmm</think>Olá!")]
        c = self.post([{"role": "user", "content": "K9 oi"}])
        self.assertEqual(c["message"]["content"], "Olá!")

    def test_sem_pensar_acrescenta_no_think(self):
        fp.CONFIG["no_think"] = True
        self.post([{"role": "user", "content": "K10 oi"}])
        self.assertTrue(FakeOllama.last_body["messages"][-1]["content"].endswith("/no_think"))

    def test_acentos_chegam_como_ascii(self):
        # alguns clientes no Windows leem UTF-8 como cp1252 ("NÃ£o"); \uXXXX evita isso
        texto = "Não foi possível: módulo ausente ✓"
        for stream in (False, True):
            SCRIPT["K11"] = [reply(texto)]
            body = {"model": "qwen3:8b", "stream": stream, "tools": TOOLS,
                    "messages": [{"role": "user", "content": "K11 oi"}]}
            req = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("ascii")   # falha se houver byte fora do ASCII
                self.assertIn("charset=utf-8", r.headers["Content-Type"])
            if stream:
                msg = json.loads(raw.splitlines()[0][len("data: "):])["choices"][0]["delta"]
            else:
                msg = json.loads(raw)["choices"][0]["message"]
            self.assertEqual(msg["content"], texto)

    def test_modelos_passam_direto(self):
        url = "http://127.0.0.1:%d/v1/models" % self.proxy.server_port
        self.assertIn("qwen3", urllib.request.urlopen(url).read().decode())


if __name__ == "__main__":
    unittest.main()
