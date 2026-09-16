import json
import shutil
from pathlib import Path

import pytest

import orquestrador.orquestrador as orq

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bubblewrap (bwrap) não instalado neste ambiente — sudo apt install bubblewrap",
)


def _msg_tool_call(id_, nome, argumentos):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}
        ],
    }


@pytest.fixture
def projeto(tmp_path: Path) -> Path:
    (tmp_path / "existente.txt").write_text("ola\n")
    return tmp_path


@pytest.fixture(autouse=True)
def _restaurar_selecionar_motor():
    original = orq.selecionar_motor
    yield
    orq.selecionar_motor = original


def test_motor_indisponivel_falha_alto_sem_travar(projeto: Path):
    orq.selecionar_motor = lambda: {"escolhido": None, "base_url": None, "mensagem": "nenhum motor"}
    with pytest.raises(orq.MotorIndisponivelError):
        orq.Orquestrador(projeto).rodar("qualquer instrução")


def test_loop_completo_escreve_arquivo_e_finaliza(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "escrever_arquivo", {"caminho": "saida.txt", "conteudo": "gerado\n"}),
            _msg_tool_call("2", "finalizar", {"resumo": "feito", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    resultado = orq.Orquestrador(projeto).rodar("crie saida.txt")

    assert resultado == {"resumo": "feito", "sucesso": True}
    assert (projeto / "saida.txt").read_text() == "gerado\n"


def test_loop_executa_comando_via_sandbox(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "executar_comando", {"comando": ["/bin/cat", "existente.txt"]}),
            _msg_tool_call("2", "finalizar", {"resumo": "verificado", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    resultado = orq.Orquestrador(projeto).rodar("leia o arquivo existente")
    assert resultado["sucesso"] is True


def test_escrita_fora_da_raiz_do_projeto_e_bloqueada(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "escrever_arquivo", {"caminho": "../../etc/passwd_teste", "conteudo": "x"}),
            _msg_tool_call("2", "finalizar", {"resumo": "tentei escapar", "sucesso": False}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    orq.Orquestrador(projeto).rodar("tente escrever fora do projeto")
    assert not Path("/etc/passwd_teste").exists()


def test_limite_de_iteracoes_e_respeitado(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [_msg_tool_call("1", "ler_arquivo", {"caminho": "existente.txt"})]  # nunca chama finalizar
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    with pytest.raises(orq.LimiteDeIteracoesError):
        orq.Orquestrador(projeto, max_iteracoes=3).rodar("nunca termine")


def test_contexto_extra_e_prependido_a_mensagem_do_usuario(projeto: Path):
    """O diagnóstico do analisador_projeto (via --diagnostico na CLI)
    precisa chegar de verdade na mensagem enviada ao modelo, não só
    existir como parâmetro aceito."""
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    capturado = {}
    resposta_finalizar = _msg_tool_call("1", "finalizar", {"resumo": "ok", "sucesso": True})

    class _HandlerCaptura(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tamanho))
            capturado["mensagens"] = corpo["messages"]
            saida = json.dumps({"choices": [{"message": resposta_finalizar}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    servidor = HTTPServer(("127.0.0.1", porta), _HandlerCaptura)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": f"http://127.0.0.1:{porta}/v1"}
        orq.Orquestrador(projeto).rodar("conserte o bug", contexto_extra="Diagnóstico: 3 funções incompletas")
    finally:
        servidor.shutdown()

    mensagem_usuario = capturado["mensagens"][1]["content"]
    assert mensagem_usuario.startswith("Diagnóstico: 3 funções incompletas")
    assert mensagem_usuario.endswith("conserte o bug")


def test_geracao_truncada_levanta_erro_em_vez_de_travar(projeto: Path):
    """Achado testando contra um modelo real (Qwen2.5-Coder-7B em
    Q4_K_M): com tool_choice=required, o modelo pode entrar em geração
    descontrolada (>1000 tokens para uma chamada que deveria ter ~15).
    max_tokens corta isso cedo; finish_reason="length" precisa virar um
    erro claro, não uma tentativa de parsear JSON incompleto."""
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    capturado = {}

    class _HandlerTruncado(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tamanho))
            capturado["max_tokens"] = corpo.get("max_tokens")
            resposta = {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": '{"name": "geracao incompleta...'},
                        "finish_reason": "length",
                    }
                ]
            }
            saida = json.dumps(resposta).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    servidor = HTTPServer(("127.0.0.1", porta), _HandlerTruncado)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": f"http://127.0.0.1:{porta}/v1"}
        with pytest.raises(orq.GeracaoTruncadaError):
            orq.Orquestrador(projeto, max_tokens_resposta=64).rodar("instrução qualquer")
    finally:
        servidor.shutdown()

    assert capturado["max_tokens"] == 64


def test_on_evento_recebe_progresso_de_cada_etapa(projeto: Path, servidor_llm_mock):
    base_url = servidor_llm_mock(
        [
            _msg_tool_call("1", "ler_arquivo", {"caminho": "existente.txt"}),
            _msg_tool_call("2", "finalizar", {"resumo": "ok", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    eventos = []
    orq.Orquestrador(projeto).rodar("leia o arquivo", on_evento=eventos.append)

    texto = "\n".join(eventos)
    assert "Motor: mock" in texto
    assert "ler_arquivo" in texto
    assert "finalizar(sucesso=True)" in texto


def test_extrair_chamada_de_texto_com_markdown_fence():
    texto = (
        '```json\n{\n  "name": "ler_arquivo",\n  "arguments": {\n    "caminho": "app.py"\n  }\n}\n```\n\n'
        "Depois disso eu vou continuar."
    )
    resultado = orq.extrair_chamada_de_texto(texto)
    assert resultado == {"name": "ler_arquivo", "arguments": {"caminho": "app.py"}}


def test_extrair_chamada_de_texto_sem_json_retorna_none():
    assert orq.extrair_chamada_de_texto("apenas uma resposta em texto, sem chamada nenhuma") is None


def test_extrair_chamada_de_texto_ignora_json_sem_formato_de_chamada():
    # um objeto JSON válido, mas que não é uma chamada de ferramenta
    # (sem "name"/"arguments") não deve ser confundido com uma
    assert orq.extrair_chamada_de_texto('{"algo": "irrelevante"}') is None


def test_loop_extrai_chamada_de_conteudo_texto_quando_servidor_nao_estrutura(projeto: Path, servidor_llm_mock):
    """Reproduz o achado real: llama-server + Qwen2.5-Coder ignoram
    tool_choice=required e devolvem a chamada como JSON dentro de
    ```json``` em message.content, sem tool_calls. O orquestrador
    precisa extrair e executar mesmo assim."""
    base_url = servidor_llm_mock(
        [
            {
                "role": "assistant",
                "content": (
                    '```json\n{"name": "escrever_arquivo", '
                    '"arguments": {"caminho": "saida.txt", "conteudo": "via texto\\n"}}\n```'
                ),
            },
            _msg_tool_call("2", "finalizar", {"resumo": "ok via extracao", "sucesso": True}),
        ]
    )
    orq.selecionar_motor = lambda: {"escolhido": "mock", "base_url": base_url}

    resultado = orq.Orquestrador(projeto).rodar("crie saida.txt")

    assert resultado == {"resumo": "ok via extracao", "sucesso": True}
    assert (projeto / "saida.txt").read_text() == "via texto\n"


def test_extracao_funciona_mesmo_com_geracao_truncada_depois_do_primeiro_bloco(projeto: Path):
    """O caso exato visto na máquina real: finish_reason="length" (o
    modelo continuou narrando depois do primeiro bloco e foi cortado),
    mas o primeiro JSON já estava completo — não deve levantar
    GeracaoTruncadaError, deve extrair e usar essa primeira chamada."""
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    conteudo_truncado = (
        '```json\n{"name": "ler_arquivo", "arguments": {"caminho": "app.py"}}\n```\n\n'
        "Depois disso, você pode chamar escrever_arquivo com o conteúdo "
        'atualizado. ```json\n{"name": "escrever_arquivo", "arguments": {"cam'
    )

    class _HandlerTruncadoComChamadaValida(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            self.rfile.read(tamanho)
            resposta = {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": conteudo_truncado},
                        "finish_reason": "length",
                    }
                ]
            }
            saida = json.dumps(resposta).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(saida)))
            self.end_headers()
            self.wfile.write(saida)

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    servidor = HTTPServer(("127.0.0.1", porta), _HandlerTruncadoComChamadaValida)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        mensagem = orq.chamar_llm(f"http://127.0.0.1:{porta}/v1", [{"role": "user", "content": "x"}])
    finally:
        servidor.shutdown()

    assert mensagem["tool_calls"][0]["function"]["name"] == "ler_arquivo"
