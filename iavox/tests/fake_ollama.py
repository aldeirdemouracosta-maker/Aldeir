"""Servidor Ollama fake, só pra validar a integração ponta a ponta em teste."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silencia logs no teste

    def do_GET(self):
        if self.path == "/api/tags":
            body = json.dumps({
                "models": [{"name": "llama3.2:3b"}, {"name": "llava:7b"}]
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        if "images" in payload:
            # simula resposta de audiodescrição
            response_text = "Gráfico de barras coloridas mostrando o crescimento de vendas ao longo de três trimestres."
        elif "perguntas de estudo" in payload.get("prompt", ""):
            # simula as perguntas do EstudaVox
            response_text = (
                "Aqui estão as perguntas:\n1. O que é o IAVOX?\n"
                "2. Como o IAVOX ajuda quem usa o DOSVOX?\n3. Por que funcionar offline é importante?"
            )
        else:
            # simula resumo
            prompt = payload.get("prompt", "")
            if "curto" in prompt.lower() or "3 a 5 frases" in prompt:
                response_text = "Resumo curto simulado: o IAVOX une DOSVOX e IA para leitura acessível de PDFs."
            else:
                response_text = "Resumo simulado (nível padrão) do texto enviado, gerado pelo Ollama fake de teste."

        body = json.dumps({"response": response_text}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def run(port=11434):
    server = HTTPServer(("localhost", port), FakeOllamaHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
