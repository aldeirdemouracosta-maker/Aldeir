import http.server
import socket
import threading

from motor_ia.selecionar_motor import MotorIA, endpoint_responde, motores_conhecidos, selecionar_motor


class _HandlerOk(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()


def test_endpoint_responde_true_quando_servidor_de_pe():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()

    servidor = http.server.HTTPServer(("127.0.0.1", porta), _HandlerOk)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        assert endpoint_responde(f"http://127.0.0.1:{porta}/") is True
    finally:
        servidor.shutdown()


def test_endpoint_responde_false_quando_nada_escutando():
    # porta alta improvável de ter algo escutando
    assert endpoint_responde("http://127.0.0.1:65000/", timeout=0.5) is False


def test_selecionar_motor_escolhe_o_primeiro_disponivel():
    motores = [
        MotorIA("A", "http://a", requisito_hardware=lambda: True, verificar_disponivel=lambda: False),
        MotorIA("B", "http://b", requisito_hardware=lambda: True, verificar_disponivel=lambda: True),
        MotorIA("C", "http://c", requisito_hardware=lambda: True, verificar_disponivel=lambda: True),
    ]
    resultado = selecionar_motor(motores)
    assert resultado["escolhido"] == "B"
    assert resultado["base_url"] == "http://b"


def test_selecionar_motor_ignora_inelegivel_mesmo_disponivel():
    motores = [
        MotorIA("SemHardware", "http://x", requisito_hardware=lambda: False, verificar_disponivel=lambda: True),
        MotorIA("ComHardware", "http://y", requisito_hardware=lambda: True, verificar_disponivel=lambda: True),
    ]
    resultado = selecionar_motor(motores)
    assert resultado["escolhido"] == "ComHardware"


def test_selecionar_motor_nenhum_disponivel():
    motores = [
        MotorIA("A", "http://a", requisito_hardware=lambda: True, verificar_disponivel=lambda: False),
    ]
    resultado = selecionar_motor(motores)
    assert resultado["escolhido"] is None
    assert "mensagem" in resultado


def test_motores_conhecidos_prioriza_llama_cpp_sobre_ollama_e_lm_studio():
    # llama.cpp (Vulkan) e o motor padrao do projeto (nao depende de AVX2) —
    # se Ollama ou LM Studio tambem estiverem de pe ao mesmo tempo, o padrao
    # nao pode perder a prioridade so por vir depois na lista.
    nomes = [motor.nome for motor in motores_conhecidos()]
    assert nomes[0] == "llama.cpp (Vulkan)"
