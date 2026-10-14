"""
ElectronicsLLM – instrutor e criador de circuitos com LLM LOCAL (Ollama).

Princípios
----------
* A IA só é chamada quando o usuário clica no botão correspondente na interface.
  Nada aqui roda sozinho; sem Ollama o app continua útil (biblioteca, lições e quiz estáticos).
* O LLM nunca é a fonte da verdade: todo netlist gerado passa por sanitização + simulação no
  ngspice e, se falhar, o erro volta ao modelo (até `max_attempts` tentativas).
* Footprints usam geradores determinísticos (core.footprints); o LLM só descreve.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.spice_engine import sanitize_netlist
from core.footprints import FootprintSpec, SUPPORTED, build_footprint
from core.library.base import CircuitDef, HELPERS
from .parsing import parse_analysis, parse_creator_response
from .retrieval import search_library
from .validation import ValidationResult, validate_netlist

try:  # o pacote só é necessário quando a IA é usada
    import ollama
except ImportError:  # pragma: no cover
    ollama = None


# Ordem de preferência (menor/mais leve primeiro dentro de cada nível de qualidade)
MODEL_NOTES = {
    "qwen2.5-coder:1.5b": "~1,0 GB – melhor para gerar netlists",
    "qwen2.5:1.5b": "~1,0 GB – bom em português",
    "llama3.2:1b": "~1,3 GB – equilibrado",
    "gemma2:2b": "~1,6 GB – instrutor mais detalhado",
    "qwen2:0.5b": "~0,35 GB – o mais leve; ideal só para explicações curtas",
    "tinyllama": "~0,64 GB – muito leve, qualidade limitada",
    "phi3:mini": "~2,2 GB – raciocínio melhor, mais pesado",
}
LIGHT_MODELS = list(MODEL_NOTES)

INSTRUCTOR_SYSTEM = (
    "Você é um instrutor de eletrônica paciente e preciso. Responda SEMPRE em português do Brasil, com "
    "linguagem simples, fórmulas curtas e unidades corretas. Use somente os dados fornecidos para afirmar "
    "números; se algo não estiver nos dados, diga que é uma estimativa. Estruture a resposta com títulos "
    "curtos em Markdown. Nunca invente valores de componentes que não foram dados."
)

CREATOR_SYSTEM = f"""Você projeta circuitos para o simulador ngspice. Responda em português do Brasil.
FORMATO OBRIGATÓRIO (nesta ordem, sem texto extra antes):
TITULO: <nome curto>
ANALISE: <tran stop=5m step=5u | ac start=10 stop=1meg points=20 | dc src=Vin start=0 stop=5 step=0.1 | op>
SONDAS: <nós para plotar, separados por vírgula>
```spice
<netlist completo>
```
EXPLICACAO: <2 a 5 frases: como funciona e o que observar>

REGRAS DO NETLIST:
- A primeira linha do bloco é o título. O nó terra é 0. Nada de .control, .include, .lib, .tran/.ac/.dc/.op/.end.
- Use valores com sufixos SPICE: k, meg, u, n, p (ex.: 10k, 100n, 1meg). Nomes de nós sem espaços.
- Toda fonte AC de entrada deve ser: Vin in 0 SIN(0 <amplitude> <freq>) AC 1
- Ligue sempre pelo menos uma fonte de tensão ou corrente, e todo nó precisa de caminho para o terra.
- Amp-op pronto: XU1 <entrada+> <entrada-> <saida> <vcc> <vee> OPAMP (alimente com fontes Vcc/Vee).
- Modelos prontos: diodos DSI, D1N4148, DSCH(Schottky), DLED; BJT QN2222(NPN) QP2907(PNP) QPOWN QPOWP;
  MOSFET: M1 d g s s NMOSP W=1 L=1 (ou PMOSP; NMLOG/PMLOG para lógica); chave: S1 a b ctrl+ ctrl- SWM.
- Fontes de pulso: Vg g 0 PULSE(0 5 0 10n 10n <largura> <periodo>).
- Fontes comportamentais: B1 out 0 V=<expressão com V(nó) e time>.
- Escolha componentes realistas e valores que funcionem (confira polarização e tensões)."""


@dataclass
class PackageSpec:
    name: str
    package_type: str
    pins: int
    pitch_mm: Optional[float]
    body_size_mm: Optional[str]
    description: str
    footprint_kicad: Optional[str] = None
    recommended_land_pattern: Optional[str] = None
    notes: Optional[str] = None
    verified: bool = True
    model_used: str = ""
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuizItem:
    pergunta: str
    opcoes: List[str]
    correta: int
    explicacao: str = ""


@dataclass
class CreatedCircuit:
    ok: bool
    title: str = ""
    netlist: str = ""
    analysis: Optional[Dict] = None
    probes: List[str] = field(default_factory=list)
    explanation: str = ""
    attempts: int = 0
    log: List[str] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    fallback: Optional[str] = None     # id de circuito da biblioteca sugerido quando a IA falha
    model_used: str = ""
    created_at: str = ""


class LLMUnavailable(RuntimeError):
    pass


class ElectronicsLLM:
    """Cliente mínimo do Ollama + comportamentos de instrutor e criador."""

    def __init__(self, model: str = "qwen2.5:1.5b", host: str = "http://localhost:11434",
                 temperature: float = 0.2, client: Any = None):
        self.model = model
        self.host = host
        self.temperature = temperature
        if client is not None:
            self.client = client
        else:
            if ollama is None:
                raise LLMUnavailable("Pacote 'ollama' não instalado (pip install ollama).")
            self.client = ollama.Client(host=host)

    # ------------------------------------------------------------------ baixo nível
    def _chat(self, system: str, user: str, json_mode: bool = False, num_predict: int = 1100,
              history: Optional[List[Dict[str, str]]] = None) -> str:
        messages = [{"role": "system", "content": system}] + (history or []) + [{"role": "user", "content": user}]
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages,
                                  "options": {"temperature": self.temperature, "num_predict": num_predict}}
        if json_mode:
            kwargs["format"] = "json"
        try:
            resp = self.client.chat(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise LLMUnavailable(
                f"Não consegui falar com o Ollama em {self.host} usando '{self.model}': {e}. "
                f"Verifique `ollama serve` e `ollama pull {self.model}`.") from e
        msg = resp["message"]["content"] if isinstance(resp, dict) else resp.message.content
        return msg.strip()

    @staticmethod
    def _extract_json(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None

    # ------------------------------------------------------------------ INSTRUTOR
    def explain_circuit(self, cdef: CircuitDef, params: Dict[str, float], theory: Dict[str, Any],
                        measured: Optional[Dict[str, Any]] = None, level: str = "iniciante") -> str:
        """Explicação passo a passo do circuito (botão 'Explicar com IA')."""
        th = "\n".join(f"- {k}: {v[0]:.4g} {v[1]}" for k, v in theory.items()) or "- (sem fórmulas cadastradas)"
        ms = "\n".join(f"- {k}: {v:.4g}" for k, v in (measured or {}).items()) or "- (ainda não simulado)"
        prm = ", ".join(f"{p.label}={params[p.key]:g} {p.unit}" for p in cdef.params)
        net = cdef.netlist(params, with_helpers=False)[:1800]
        user = (f"Nível do aluno: {level}.\nCircuito: {cdef.name}\nResumo: {cdef.summary}\nParâmetros: {prm}\n"
                f"Valores teóricos calculados:\n{th}\nMedições da simulação:\n{ms}\nNetlist:\n{net}\n\n"
                "Explique em 5 seções curtas: 1) O que o circuito faz; 2) Como funciona (passo a passo); "
                "3) Como ler os gráficos desta simulação; 4) Dois experimentos para o aluno tentar; "
                "5) Erros comuns. Compare os valores medidos com os teóricos.")
        return self._chat(INSTRUCTOR_SYSTEM, user, num_predict=1100)

    def answer(self, question: str, cdef: Optional[CircuitDef] = None, params: Optional[Dict[str, float]] = None,
               history: Optional[List[Dict[str, str]]] = None) -> str:
        ctx = ""
        if cdef:
            ctx = (f"Contexto: o aluno está estudando '{cdef.name}' ({cdef.summary}). "
                   f"Netlist:\n{cdef.netlist(params, with_helpers=False)[:1500]}\n")
        return self._chat(INSTRUCTOR_SYSTEM, f"{ctx}Pergunta do aluno: {question}", num_predict=700, history=history)

    def quiz(self, cdef: CircuitDef, params: Dict[str, float], n: int = 3) -> List[QuizItem]:
        """Quiz gerado pela IA (botão). Valida o JSON; em caso de falha levanta ValueError."""
        th = "; ".join(f"{k} = {v[0]:.4g} {v[1]}" for k, v in cdef.theory_values(params).items())
        user = (f"Crie {n} perguntas de múltipla escolha (4 opções) sobre o circuito '{cdef.name}': {cdef.summary} "
                f"Dados corretos: {th}. Responda em JSON: "
                '{"perguntas":[{"pergunta":"...","opcoes":["a","b","c","d"],"correta":0,"explicacao":"..."}]}')
        last = ""
        for _ in range(2):
            raw = self._chat(INSTRUCTOR_SYSTEM, user, json_mode=True, num_predict=900)
            data = self._extract_json(raw)
            items = self._parse_quiz(data)
            if items:
                return items
            last = raw
            user += "\nSua resposta anterior não seguiu o formato JSON pedido. Responda apenas o JSON."
        raise ValueError(f"O modelo não retornou um quiz válido: {last[:120]}")

    @staticmethod
    def _parse_quiz(data: Any) -> List[QuizItem]:
        items: List[QuizItem] = []
        if not isinstance(data, dict):
            return items
        for q in data.get("perguntas", []) or []:
            try:
                opts = [str(o) for o in q["opcoes"]][:4]
                c = int(q["correta"])
                if len(opts) >= 2 and 0 <= c < len(opts) and q["pergunta"]:
                    items.append(QuizItem(str(q["pergunta"]), opts, c, str(q.get("explicacao", ""))))
            except (KeyError, TypeError, ValueError):
                continue
        return items

    def explain_waveform(self, stats: Dict[str, float], channel: str, circuit_name: str = "") -> str:
        st = ", ".join(f"{k}={v:.4g}" for k, v in stats.items())
        return self._chat(INSTRUCTOR_SYSTEM,
                          f"Circuito: {circuit_name}. Canal '{channel}'. Medições: {st}. Interprete a forma de onda: "
                          "o que ela indica sobre o funcionamento, distorção, ondulação e possíveis problemas.", num_predict=600)

    def read_circuit(self, netlist: str) -> str:
        """Descreve um netlist qualquer (botão 'Analisar circuito')."""
        return self._chat(INSTRUCTOR_SYSTEM,
                          "Leia este netlist SPICE e descreva: função do circuito, função de cada bloco, tensões/correntes "
                          f"esperadas e melhorias possíveis.\n```spice\n{netlist[:3000]}\n```", num_predict=900)

    # ------------------------------------------------------------------ CRIADOR
    def create_circuit(self, request: str, max_attempts: int = 3,
                       on_attempt: Optional[Callable[[int, str], None]] = None,
                       validator: Callable[..., ValidationResult] = validate_netlist) -> CreatedCircuit:
        """
        Cria um circuito a partir da descrição do usuário (botão 'Criar com IA'):
        recuperação de exemplos reais → geração → validação no ngspice → correção com o erro.
        """
        out = CreatedCircuit(ok=False, model_used=self.model, created_at=datetime.now().isoformat(timespec="seconds"))
        hits = search_library(request, k=2)
        example = ""
        if hits:
            ex = hits[0][1]
            example = (f"\nExemplo VÁLIDO parecido ('{ex.name}'), use como referência de estilo:\n```spice\n"
                       f"{ex.netlist(with_helpers=False)[:1500]}\n```\n")
            out.fallback = ex.id
        user = f"Pedido do usuário: {request}\n{example}\nCrie o circuito completo no formato obrigatório."
        history: List[Dict[str, str]] = []
        for attempt in range(1, max_attempts + 1):
            out.attempts = attempt
            raw = self._chat(CREATOR_SYSTEM, user, num_predict=1400, history=history)
            if on_attempt:
                on_attempt(attempt, raw)
            parsed = parse_creator_response(raw)
            if not parsed["netlist"]:
                out.log.append(f"Tentativa {attempt}: resposta sem netlist.")
                history += [{"role": "user", "content": user}, {"role": "assistant", "content": raw[:1500]}]
                user = "Sua resposta não trouxe o bloco ```spice. Responda de novo no formato obrigatório."
                continue
            analysis = parse_analysis(parsed["analise"])
            v = validator(parsed["netlist"], analysis, parsed["sondas"] or None)
            if v.ok:
                out.ok = True
                out.title = parsed["titulo"] or request[:60]
                out.netlist = sanitize_netlist(parsed["netlist"]).text()   # versão segura, sem .control etc.
                out.analysis = v.analysis
                out.probes = [p for p in parsed["sondas"] if p in v.nodes] or v.nodes[:3]
                out.explanation = parsed["explicacao"]
                out.validation = v
                out.log.append(f"Tentativa {attempt}: válido.")
                return out
            out.log.append(f"Tentativa {attempt}: {v.message}")
            out.netlist = parsed["netlist"]
            history += [{"role": "user", "content": user}, {"role": "assistant", "content": raw[:2000]}]
            user = (f"O simulador rejeitou o netlist: {v.message}\nCorrija o problema e responda novamente com o circuito "
                    "COMPLETO no mesmo formato obrigatório.")
        out.explanation = ("A IA local não conseguiu produzir um netlist que simule corretamente. "
                           + (f"O circuito mais parecido da biblioteca é '{hits[0][1].name}'." if hits else ""))
        return out

    # ------------------------------------------------------------------ PACOTES
    def create_package(self, request: str, describe: bool = False) -> PackageSpec:
        """
        Footprint: geometria SEMPRE do gerador determinístico quando o pacote é reconhecido.
        Com `describe=True` o LLM acrescenta notas de uso (botão 'Descrever com IA').
        """
        now = datetime.now().isoformat(timespec="seconds")
        try:
            fp: FootprintSpec = build_footprint(request)
        except ValueError as e:
            raise ValueError(f"{e}\nPacotes suportados: {', '.join(SUPPORTED)}") from e
        notes = None
        if describe:
            notes = self._chat(INSTRUCTOR_SYSTEM,
                               f"Em até 4 frases, explique quando usar o pacote {fp.name} ({fp.description}) e cuidados de "
                               "layout/solda (pasta de solda, terra térmico, espaçamento).", num_predict=300)
        return PackageSpec(
            name=fp.name, package_type=fp.package_type, pins=fp.pins, pitch_mm=fp.pitch_mm,
            body_size_mm=f"{fp.body_mm[0]}x{fp.body_mm[1]}", description=fp.description,
            footprint_kicad=fp.to_kicad(), recommended_land_pattern="Geometria IPC-7351 nominal (gerador CircuitForge)",
            notes=notes, verified=True, model_used=self.model if describe else "", created_at=now)

    # compatibilidade com a API anterior
    def generate_netlist(self, description: str) -> CreatedCircuit:
        return self.create_circuit(description)


# ----------------------------------------------------------------------------------------
# Funções utilitárias
# ----------------------------------------------------------------------------------------

def installed_models(host: str = "http://localhost:11434") -> List[Dict[str, Any]]:
    """Modelos instalados no Ollama: [{'name', 'size_gb'}]."""
    if ollama is None:
        return []
    try:
        res = ollama.Client(host=host).list()
    except Exception:  # noqa: BLE001
        return []
    models = res["models"] if isinstance(res, dict) else getattr(res, "models", [])
    out = []
    for m in models:
        name = m.get("model") or m.get("name") if isinstance(m, dict) else (getattr(m, "model", None) or getattr(m, "name", ""))
        size = m.get("size", 0) if isinstance(m, dict) else getattr(m, "size", 0)
        out.append({"name": name, "size_gb": (size or 0) / 1e9})
    return out


def list_light_models(host: str = "http://localhost:11434") -> List[str]:
    return [m["name"] for m in installed_models(host)]


def recommend_model(installed: Optional[List[str]] = None) -> str:
    installed = installed if installed is not None else list_light_models()
    names = {n.split(":latest")[0]: n for n in installed}
    for pref in LIGHT_MODELS:
        if pref in names:
            return names[pref]
        base = pref.split(":")[0]
        for k, v in names.items():
            if k.split(":")[0] == base:
                return v
    return installed[0] if installed else "qwen2.5:1.5b"


def ollama_online(host: str = "http://localhost:11434") -> bool:
    if ollama is None:
        return False
    try:
        ollama.Client(host=host).list()
        return True
    except Exception:  # noqa: BLE001
        return False
