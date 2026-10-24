"""
ElectronicsLLM – LLM local leve (<1 GB) especializado em:
- Criação de pacotes eletrônicos (footprints / packages)
- Leitura e descrição de circuitos e placas
- Geração de netlists e documentação técnica

Modelos recomendados (quantizados < 1 GB):
  - qwen2:0.5b          (~350 MB)
  - phi3:mini           (~2.2 GB Q4 → use phi3:mini-q4 se disponível, ou tinyllama)
  - tinyllama           (~637 MB)
  - gemma2:2b           (Q4 ~1.3 GB – limite)
  - llama3.2:1b         (~1.3 GB – limite superior)

Para treino/fine-tune futuro: dataset de datasheets + footprints KiCad + netlists.
"""

from __future__ import annotations
import json
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import ollama


# Modelos leves prioritários (< ~1 GB quantizado)
LIGHT_MODELS = [
    "qwen2:0.5b",
    "tinyllama",
    "llama3.2:1b",
    "phi3:mini",
    "gemma2:2b",
]


@dataclass
class PackageSpec:
    """Especificação de um pacote eletrônico gerado."""
    name: str
    package_type: str          # SMD, THT, BGA, etc.
    pins: int
    pitch_mm: Optional[float]
    body_size_mm: Optional[str]
    description: str
    footprint_kicad: Optional[str] = None
    recommended_land_pattern: Optional[str] = None
    notes: Optional[str] = None
    model_used: str = ""
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CircuitReading:
    """Resultado da leitura/descrição de um circuito."""
    summary: str
    components: List[str]
    topology: str
    function: str
    suggestions: List[str]
    netlist_hint: Optional[str] = None
    model_used: str = ""
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ElectronicsLLM:
    """
    Interface especializada para tarefas de eletrônica com LLM local leve.
    """

    def __init__(
        self,
        model: str = "qwen2:0.5b",
        temperature: float = 0.25,
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.temperature = temperature
        self.client = ollama.Client(host=host)

    # ------------------------------------------------------------------
    # Prompts especializados (treinados via prompt engineering)
    # ------------------------------------------------------------------

    def _prompt_create_package(
        self,
        component_name: str,
        package_hint: str = "",
        pins: Optional[int] = None,
        extra: str = "",
    ) -> str:
        pins_txt = f"{pins} pinos" if pins else "número de pinos a inferir"
        return f"""Você é um especialista em encapsulamentos eletrônicos e footprints (KiCad / IPC).
Sua única função é criar especificações precisas de pacotes eletrônicos.

Componente: {component_name}
Dica de pacote: {package_hint or "não informada"}
Pinos: {pins_txt}
Extra: {extra or "nenhuma"}

Gere uma especificação completa no formato JSON estrito:
{{
  "name": "nome do footprint (ex: SOIC-8_3.9x4.9mm_P1.27mm)",
  "package_type": "SMD|THT|BGA|QFN|SOP|DIP|etc",
  "pins": número,
  "pitch_mm": valor ou null,
  "body_size_mm": "LxW" ou null,
  "description": "descrição técnica curta",
  "footprint_kicad": "trecho de código KiCad s-expression simplificado ou null",
  "recommended_land_pattern": "descrição do land pattern IPC",
  "notes": "observações de fabricação ou soldagem"
}}

Responda APENAS com o JSON válido. Sem texto extra."""

    def _prompt_read_circuit(
        self,
        description_or_netlist: str,
        context: str = "",
    ) -> str:
        return f"""Você é um engenheiro eletrônico sênior especializado em leitura de esquemas e placas.
Analise o circuito abaixo e responda de forma técnica e objetiva.

CIRCUITO / NETLIST / DESCRIÇÃO:
{description_or_netlist}

CONTEXTO ADICIONAL:
{context or "nenhum"}

Responda APENAS com JSON válido:
{{
  "summary": "resumo em 1-2 frases do que o circuito faz",
  "components": ["lista", "dos", "principais", "componentes"],
  "topology": "topologia (ex: filtro RC passa-baixa, amplificador inversor, fonte chaveada...)",
  "function": "função principal do circuito",
  "suggestions": ["melhoria 1", "melhoria 2"],
  "netlist_hint": "sugestão de netlist SPICE simplificado ou null"
}}

Não invente componentes que não estejam presentes. Seja rigoroso."""

    def _prompt_generate_netlist(
        self,
        description: str,
        analysis_type: str = "transient",
    ) -> str:
        return f"""Você é um gerador de netlists SPICE preciso.
A partir da descrição, gere um netlist SPICE3/ngspice válido e mínimo.

DESCRIÇÃO DO CIRCUITO:
{description}

TIPO DE ANÁLISE DESEJADA: {analysis_type}

Regras:
- Use apenas dispositivos básicos (R, C, L, V, I, D, Q, M) ou subcircuitos padrão.
- Inclua .tran, .ac ou .op conforme o tipo.
- Nós numerados ou nomeados de forma clara.
- Termine com .end

Responda APENAS com o netlist puro, sem markdown e sem explicações."""

    def _prompt_explain_waveform(
        self,
        circuit_desc: str,
        measurements: Dict[str, float],
    ) -> str:
        meas_txt = "\n".join(f"- {k}: {v:.4g}" for k, v in measurements.items())
        return f"""Você é um especialista em análise de formas de onda e debug de circuitos.

CIRCUITO:
{circuit_desc}

MEDIÇÕES DO OSCILOSCÓPIO:
{meas_txt}

Explique em português (máximo 120 palavras):
1. O que a forma de onda indica sobre o comportamento do circuito.
2. Se há algo anormal (clipping, offset, frequência errada, etc.).
3. Uma hipótese de causa se houver problema.

Seja técnico e direto."""

    # ------------------------------------------------------------------
    # Chamadas
    # ------------------------------------------------------------------

    def _call(self, prompt: str, json_mode: bool = False) -> str:
        options = {
            "temperature": self.temperature,
            "num_predict": 1024,
        }
        kwargs: Dict[str, Any] = {}
        if json_mode:
            kwargs["format"] = "json"
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options=options,
            **kwargs,
        )
        return response["message"]["content"].strip()

    def _extract_json(self, text: str) -> Dict[str, Any]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def create_package(
        self,
        component_name: str,
        package_hint: str = "",
        pins: Optional[int] = None,
        extra: str = "",
    ) -> PackageSpec:
        """Gera especificação de pacote/footprint eletrônico."""
        prompt = self._prompt_create_package(component_name, package_hint, pins, extra)
        raw = self._call(prompt, json_mode=True)
        data = self._extract_json(raw)

        return PackageSpec(
            name=data.get("name", f"{component_name}_package"),
            package_type=data.get("package_type", "unknown"),
            pins=_to_int(data.get("pins"), pins or 0),
            pitch_mm=data.get("pitch_mm"),
            body_size_mm=data.get("body_size_mm"),
            description=data.get("description", ""),
            footprint_kicad=data.get("footprint_kicad"),
            recommended_land_pattern=data.get("recommended_land_pattern"),
            notes=data.get("notes"),
            model_used=self.model,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )

    def read_circuit(
        self,
        description_or_netlist: str,
        context: str = "",
    ) -> CircuitReading:
        """Lê e interpreta um circuito ou netlist."""
        prompt = self._prompt_read_circuit(description_or_netlist, context)
        raw = self._call(prompt, json_mode=True)
        data = self._extract_json(raw)

        return CircuitReading(
            summary=data.get("summary", ""),
            components=data.get("components", []),
            topology=data.get("topology", ""),
            function=data.get("function", ""),
            suggestions=data.get("suggestions", []),
            netlist_hint=data.get("netlist_hint"),
            model_used=self.model,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )

    def generate_netlist(
        self,
        description: str,
        analysis_type: str = "transient",
    ) -> str:
        """Gera netlist SPICE a partir de descrição em linguagem natural."""
        prompt = self._prompt_generate_netlist(description, analysis_type)
        return self._call(prompt)

    def explain_waveform(
        self,
        circuit_desc: str,
        measurements: Dict[str, float],
    ) -> str:
        """Explica resultados de osciloscópio / medições."""
        prompt = self._prompt_explain_waveform(circuit_desc, measurements)
        return self._call(prompt)

    def suggest_modification(
        self,
        circuit_description: str,
        user_goal: str,
    ) -> str:
        """Sugere modificações em linguagem natural para um circuito."""
        prompt = f"""Você é um engenheiro eletrônico sênior especializado em melhoria de circuitos de áudio e power.

CIRCUITO ATUAL:
{circuit_description}

OBJETIVO DO USUÁRIO:
{user_goal}

Responda em português, de forma clara e técnica, com:
1. Diagnóstico breve do circuito atual
2. Lista numerada de modificações recomendadas (componente + valor aproximado + motivo)
3. Benefícios esperados
4. Cuidados / riscos
5. Sugestão de ordem de implementação

Seja prático e realista. Não invente componentes impossíveis."""
        return self._call(prompt)

    def analyze_circuit_photo(
        self,
        image_base64: str,
        extra_question: str = "",
        vision_model: str = "llava",
    ) -> str:
        """
        Analisa foto de placa/circuito usando modelo de visão (Ollama).
        Requer modelo com suporte a imagem: llava, bakllava, qwen2-vl, moondream, etc.
        """
        prompt = f"""Você é um engenheiro eletrônico especializado em engenharia reversa de placas.

Analise a imagem do circuito/placa e descreva:
1. Tipo de circuito provável (amplificador, fonte, rádio, etc.)
2. Componentes principais visíveis (ICs, transistores, capacitores, indutores, conectores)
3. Possível topologia
4. Pontos de melhoria óbvios (se houver)
5. Riscos ou cuidados ao modificar

{extra_question or ""}

Responda em português, de forma estruturada e objetiva."""

        try:
            response = self.client.chat(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_base64],
                    }
                ],
                options={"temperature": self.temperature, "num_predict": 1024},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return (
                f"Erro ao analisar a imagem com o modelo '{vision_model}': {e}\n\n"
                "Certifique-se de que um modelo de visão está instalado, por exemplo:\n"
                "  ollama pull llava\n"
                "  ollama pull moondream\n"
                "  ollama pull qwen2-vl"
            )


def _to_int(value: Any, default: int = 0) -> int:
    """Converte para int tolerando saídas de LLM como '8 pinos'."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    m = re.search(r"\d+", str(value or ""))
    return int(m.group(0)) if m else default


def list_light_models(host: str = "http://localhost:11434") -> List[str]:
    """Lista modelos disponíveis que são candidatos leves."""
    try:
        client = ollama.Client(host=host)
        models = client.list()
        # ollama>=0.4 usa o campo "model"; versões antigas usam "name"
        names = [m.get("model") or m.get("name") for m in models.get("models", [])]
        names = [n for n in names if n]
        # Prioriza os da lista LIGHT_MODELS
        light = [n for n in names if any(lm in n for lm in LIGHT_MODELS)]
        return light or names
    except Exception:
        return []


def recommend_model() -> str:
    """Retorna o modelo leve mais recomendado para o projeto."""
    return "qwen2:0.5b"  # ~350 MB, excelente custo/benefício para 2026
