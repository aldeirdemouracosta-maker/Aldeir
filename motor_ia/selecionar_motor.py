#!/usr/bin/env python3
"""Seletor automatico de motor de IA local (llama.cpp / Ollama / LM Studio).

Detecta o hardware disponivel e os motores em execucao, e escolhe o
melhor sem exigir mudanca de codigo no orquestrador.

Nesta maquina hoje (Xeon sem AVX2 + RX 580 via Vulkan), so o llama.cpp
e elegivel. Apos um upgrade de hardware (CPU com AVX2, por exemplo),
o mesmo script passa a habilitar LM Studio e/ou Ollama automaticamente,
bastando que o motor esteja instalado e rodando.

Uso:
    python3 selecionar_motor.py
"""

import json
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional


def tem_avx2() -> bool:
    """AVX2 e exigido pelo LM Studio em Linux/Windows x64."""
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/cpuinfo") as f:
            return "avx2" in f.read()
    except OSError:
        return False


def tem_vulkan() -> bool:
    """Vulkan funcional e o requisito do backend do llama.cpp usado aqui."""
    vulkaninfo = shutil.which("vulkaninfo")
    if not vulkaninfo:
        return False
    try:
        resultado = subprocess.run(
            [vulkaninfo, "--summary"], capture_output=True, timeout=5
        )
        return resultado.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def endpoint_responde(url: str, timeout: float = 1.5) -> bool:
    """Verifica se uma API local (OpenAI-compatible) esta de pe."""
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


@dataclass
class MotorIA:
    nome: str
    base_url: str
    requisito_hardware: Callable[[], bool]
    verificar_disponivel: Callable[[], bool]
    observacao: str = ""

    def elegivel(self) -> bool:
        return self.requisito_hardware()

    def disponivel(self) -> bool:
        return self.elegivel() and self.verificar_disponivel()


def motores_conhecidos() -> list:
    """Ordem de prioridade quando mais de um estiver disponivel ao mesmo
    tempo. LM Studio e Ollama sao opcoes futuras: hoje ficam de fora
    automaticamente por falta de AVX2 ou por nao estarem rodando, e
    entram sozinhas quando o hardware/instalacao permitir.
    """
    return [
        MotorIA(
            nome="LM Studio",
            base_url="http://localhost:1234/v1",
            requisito_hardware=tem_avx2,
            verificar_disponivel=lambda: endpoint_responde(
                "http://localhost:1234/v1/models"
            ),
            observacao="Exige AVX2 (Linux/Windows x64). Opcao futura pos-upgrade.",
        ),
        MotorIA(
            nome="Ollama",
            base_url="http://localhost:11434/v1",
            requisito_hardware=lambda: True,
            verificar_disponivel=lambda: endpoint_responde(
                "http://localhost:11434/api/tags"
            ),
            observacao="Backend Vulkan ainda experimental (2026). Opcao futura/paralela.",
        ),
        MotorIA(
            nome="llama.cpp (Vulkan)",
            base_url="http://localhost:8080/v1",
            requisito_hardware=tem_vulkan,
            verificar_disponivel=lambda: endpoint_responde(
                "http://localhost:8080/v1/models"
            ),
            observacao="Motor padrao atual: nao depende de AVX2, usa RADV/Mesa.",
        ),
    ]


def selecionar_motor(motores: Optional[list] = None) -> dict:
    motores = motores or motores_conhecidos()
    diagnostico = []
    for motor in motores:
        elegivel = motor.elegivel()
        disponivel = elegivel and motor.verificar_disponivel()
        diagnostico.append(
            {
                "nome": motor.nome,
                "elegivel_pelo_hardware": elegivel,
                "servidor_respondendo": disponivel,
                "observacao": motor.observacao,
            }
        )
        if disponivel:
            return {
                "escolhido": motor.nome,
                "base_url": motor.base_url,
                "diagnostico": diagnostico,
            }
    return {
        "escolhido": None,
        "base_url": None,
        "diagnostico": diagnostico,
        "mensagem": (
            "Nenhum motor elegivel esta respondendo. Suba o servidor do "
            "llama.cpp (ex.: `llama-server -m modelo.gguf --port 8080`) "
            "ou instale/inicie um dos motores futuros (Ollama, LM Studio)."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(selecionar_motor(), indent=2, ensure_ascii=False))
