import http.server
import socket
import threading

from pathlib import Path

from motor_ia.selecionar_motor import (
    MotorIA,
    encerrar_processos_llama_server,
    endpoint_responde,
    listar_processos_llama_server,
    motores_conhecidos,
    selecionar_motor,
    temperatura_gpu_celsius,
)


def _criar_processo_falso(raiz_proc: Path, pid: int, argv: list) -> None:
    pasta = raiz_proc / str(pid)
    pasta.mkdir()
    (pasta / "cmdline").write_bytes("\x00".join(argv).encode() + b"\x00")


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


def test_listar_processos_llama_server_sem_proc_devolve_vazio(tmp_path: Path):
    assert listar_processos_llama_server(tmp_path / "nao_existe") == []


def test_listar_processos_llama_server_ignora_processos_que_nao_sao_llama_server(tmp_path: Path):
    _criar_processo_falso(tmp_path, 111, ["/usr/bin/python3", "app.py"])

    assert listar_processos_llama_server(tmp_path) == []


def test_listar_processos_llama_server_detecta_sem_limite_de_gpu(tmp_path: Path):
    _criar_processo_falso(
        tmp_path, 222, ["/home/linux/llama.cpp/build/bin/llama-server", "-m", "modelo.gguf", "--port", "8080"]
    )

    processos = listar_processos_llama_server(tmp_path)

    assert len(processos) == 1
    assert processos[0]["pid"] == 222
    assert processos[0]["porta"] == 8080
    assert processos[0]["tem_limite_gpu"] is False


def test_listar_processos_llama_server_detecta_com_limite_de_gpu(tmp_path: Path):
    _criar_processo_falso(
        tmp_path,
        333,
        ["/home/linux/llama.cpp/build/bin/llama-server", "-m", "modelo.gguf", "--port", "8080", "-ngl", "20"],
    )

    processos = listar_processos_llama_server(tmp_path)

    assert processos[0]["tem_limite_gpu"] is True


def test_listar_processos_llama_server_reconhece_flag_longa_de_limite(tmp_path: Path):
    _criar_processo_falso(
        tmp_path,
        444,
        ["/usr/bin/llama-server", "-m", "modelo.gguf", "--n-gpu-layers", "20"],
    )

    processos = listar_processos_llama_server(tmp_path)

    assert processos[0]["tem_limite_gpu"] is True


def test_listar_processos_llama_server_varios_processos(tmp_path: Path):
    _criar_processo_falso(tmp_path, 555, ["/usr/bin/llama-server", "-m", "a.gguf", "--port", "8080"])
    _criar_processo_falso(
        tmp_path, 666, ["/usr/bin/llama-server", "-m", "b.gguf", "--port", "8081", "-ngl", "20"]
    )
    _criar_processo_falso(tmp_path, 777, ["/usr/bin/bash"])

    processos = listar_processos_llama_server(tmp_path)

    assert {p["pid"] for p in processos} == {555, 666}


def test_encerrar_processos_llama_server_manda_sinal_em_cada_pid(tmp_path: Path):
    _criar_processo_falso(tmp_path, 555, ["/usr/bin/llama-server", "-m", "a.gguf", "--port", "8080"])
    _criar_processo_falso(tmp_path, 666, ["/usr/bin/llama-server", "-m", "b.gguf", "--port", "8081"])
    _criar_processo_falso(tmp_path, 777, ["/usr/bin/bash"])

    recebidos = []
    encerrados = encerrar_processos_llama_server(
        tmp_path, sinal=15, matar=lambda pid, sinal: recebidos.append((pid, sinal))
    )

    assert sorted(recebidos) == [(555, 15), (666, 15)]
    assert sorted(encerrados) == [555, 666]


def test_encerrar_processos_llama_server_ignora_falha_de_um_pid(tmp_path: Path):
    _criar_processo_falso(tmp_path, 555, ["/usr/bin/llama-server", "-m", "a.gguf", "--port", "8080"])
    _criar_processo_falso(tmp_path, 666, ["/usr/bin/llama-server", "-m", "b.gguf", "--port", "8081"])

    def matar_falso(pid, sinal):
        if pid == 555:
            raise OSError("processo já morreu")

    encerrados = encerrar_processos_llama_server(tmp_path, matar=matar_falso)

    assert encerrados == [666]


def test_encerrar_processos_llama_server_sem_processos_devolve_vazio(tmp_path: Path):
    assert encerrar_processos_llama_server(tmp_path, matar=lambda pid, sinal: None) == []


def test_temperatura_gpu_celsius_sem_sysfs_devolve_none(tmp_path: Path):
    assert temperatura_gpu_celsius(tmp_path / "nao_existe") is None


def test_temperatura_gpu_celsius_le_sensor(tmp_path: Path):
    hwmon = tmp_path / "card0" / "device" / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "temp1_input").write_text("65000\n")

    assert temperatura_gpu_celsius(tmp_path) == 65.0


def test_temperatura_gpu_celsius_usa_a_maior_entre_varias_gpus(tmp_path: Path):
    hwmon0 = tmp_path / "card0" / "device" / "hwmon" / "hwmon0"
    hwmon0.mkdir(parents=True)
    (hwmon0 / "temp1_input").write_text("60000\n")

    hwmon1 = tmp_path / "card1" / "device" / "hwmon" / "hwmon1"
    hwmon1.mkdir(parents=True)
    (hwmon1 / "temp1_input").write_text("91000\n")

    assert temperatura_gpu_celsius(tmp_path) == 91.0


def test_temperatura_gpu_celsius_ignora_sensor_ilegivel(tmp_path: Path):
    hwmon = tmp_path / "card0" / "device" / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "temp1_input").write_text("não é número")

    assert temperatura_gpu_celsius(tmp_path) is None
