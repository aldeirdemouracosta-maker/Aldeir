"""Assistente de prompts em diálogo.

A cada fala do usuário, a ficha do vídeo (vocabulario.CAMPOS) é preenchida e
o assistente pergunta o que ainda falta. Dois motores:
- regras (sempre disponível): reconhece palavras-chave e separa
  "quem / faz o quê / onde" numa frase simples;
- LLM local (Qwen via llama-server): entende frases livres e faz a próxima
  pergunta. A resposta é JSON validado por schema; nada é executado.
No fim, modelos.montar() gera o prompt no formato do modelo escolhido; o LLM
pode, opcionalmente, reescrevê-lo em inglês corrido (refino).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List, Optional

from minivideo_especialistas import schema
from minivideo_especialistas.llm import ClienteLLM, LLMIndisponivel

from . import modelos
from . import vocabulario as voc

SCHEMAS = os.path.join(os.path.dirname(__file__), "schemas")
FORMATO = "minivideo-prompt/1"
PULAR = {"", "pular", "pula", "tanto faz", "qualquer", "nao sei", "nenhum", "nada", "-"}

CONVERSA_SISTEMA = (
    "Você é o assistente de prompts de um editor de vídeo local. A cada fala do usuário, atualize a "
    "ficha do vídeo só com o que ele disse; não invente detalhes. Nos campos de escolha use exatamente "
    "um dos rótulos listados. Depois escreva UMA pergunta curta, em português, sobre o campo mais "
    "importante que ainda falta (ordem: assunto, acao, cenario, estilo, periodo, luz, plano, angulo, "
    "movimento, tom, orientacao, duracao_s, evitar). Se nada faltar, deixe a pergunta vazia. "
    "Responda somente com o objeto JSON do schema."
)
REFINO_SISTEMA = (
    "You are a cinematographer writing a prompt for a text-to-video model. Rewrite the draft as one "
    "flowing paragraph in English, in chronological order: the main action first, then movements and "
    "gestures, the appearance of the subjects, the background, camera angle and movement, lighting and "
    "colors. Keep every fact from the draft, add no new subjects, no mood or literary commentary, at most "
    "150 words. Answer only with the JSON object of the schema."
)

_LOCAL = re.compile(r"\s(na|no|nas|nos|numa|num|em|dentro d[aeo]s?|sobre|perto d[aeo]s?|ao lado d[aeo]s?)\s")
_GERUNDIO = re.compile(r"\b\w+(ando|endo|indo|ondo)\b")


def separar(frase: str) -> Dict[str, str]:
    """Heurística simples: "um cachorro correndo na praia" → assunto/ação/cenário."""
    f = " " + frase.strip().rstrip(".") + " "
    out: Dict[str, str] = {}
    m = _LOCAL.search(f)
    antes = f[:m.start()] if m else f
    if m:
        out["cenario"] = f[m.start():].strip()
    g = _GERUNDIO.search(antes)
    if g:
        out["assunto"] = antes[:g.start()].strip()
        out["acao"] = antes[g.start():].strip()
    else:
        out["assunto"] = antes.strip()
    return {k: v for k, v in out.items() if v}


class Conversa:
    def __init__(self, modelo: str = modelos.PADRAO, cliente: Optional[ClienteLLM] = None, modo: str = "auto"):
        if modelo not in modelos.MODELOS:
            raise ValueError(f"modelo desconhecido: {modelo}")
        self.modelo = modelo
        self.cliente = cliente
        self.modo = modo
        self.ficha: Dict[str, str] = {}
        self.pulados: set = set()
        self.dialogo: List[Dict[str, str]] = []
        self.pendente: Optional[str] = None
        self.registros: List[Dict] = []
        self.usou_llm = False

    # ----- estado -----
    @property
    def llm_ativo(self) -> bool:
        return self.modo != "regras" and self.cliente is not None and self.cliente.configurado

    def faltando(self) -> List[str]:
        return [c for c in voc.ORDEM if c not in self.ficha and c not in self.pulados]

    def obrigatorios_ok(self) -> bool:
        return all(self.ficha.get(c) for c, (_, obrig, _) in voc.CAMPOS.items() if obrig)

    def _diz(self, texto: str) -> str:
        self.dialogo.append({"papel": "assistente", "texto": texto})
        return texto

    def abrir(self) -> str:
        nome = modelos.MODELOS[self.modelo]["nome"]
        return self._diz(f"Olá! Vou montar o prompt para {nome}. Descreva o vídeo com suas palavras "
                         "(ex.: um cachorro correndo na praia). Comandos: /pronto, /modelo, /ficha, /novo.")

    def pergunta(self, campo: str) -> str:
        texto, _, ops = voc.CAMPOS[campo]
        if ops:
            lista = "  ".join(f"{i}) {r}" for i, (r, _, _) in enumerate(ops, 1))
            texto = f"{texto}  {lista}  (número, palavra ou 'pular')"
        return texto

    # ----- turno -----
    def responder(self, texto: str) -> str:
        texto = texto.strip()
        self.dialogo.append({"papel": "usuario", "texto": texto})
        if texto.startswith("/"):
            return self._comando(texto)
        if self.llm_ativo:
            try:
                return self._turno_llm(texto)
            except LLMIndisponivel as exc:
                if self.modo == "qwen":
                    raise
                self.registros.append({"papel": "conversa", "erro": str(exc), "fallback": "regras"})
        return self._turno_regras(texto)

    def _turno_regras(self, texto: str) -> str:
        n = voc.normalizar(texto)
        campo = self.pendente
        if campo == "assunto" and n not in PULAR and not self.ficha.get("assunto"):
            campo = None  # resposta a "quem aparece?" é uma descrição livre: separa quem/ação/lugar
        if campo:
            if n in PULAR:
                self.pulados.add(campo)
            elif voc.opcoes(campo):
                escolha = voc.escolher(campo, texto)
                if escolha:
                    self.ficha[campo] = escolha
                else:
                    # a resposta pode falar de outro campo ("drone" quando perguntei o plano)
                    novos = {k: v for k, v in voc.reconhecer(texto).items() if k not in self.ficha}
                    if not novos:
                        return self._diz(f"Não entendi. {self.pergunta(campo)}")
                    self.ficha.update(novos)
                    nomes = ", ".join(f"{k} = {v}" for k, v in novos.items())
                    return self._diz(f"Anotei {nomes}. {self.pergunta(campo)}")
            elif campo == "duracao_s":
                m = re.search(r"\d+", texto)
                if not m:
                    return self._diz(f"Use um número de segundos. {self.pergunta(campo)}")
                self.ficha[campo] = m.group(0)
            else:
                self.ficha[campo] = texto
        elif not self.ficha.get("assunto"):
            for k, v in separar(texto).items():
                self.ficha.setdefault(k, v)
        # palavras reconhecidas em qualquer fala preenchem campos ainda vazios
        for k, v in voc.reconhecer(texto).items():
            self.ficha.setdefault(k, v)
        return self._proxima()

    def _turno_llm(self, texto: str) -> str:
        opcoes = {c: [r for r, _, _ in voc.opcoes(c)] for c in voc.ORDEM if voc.opcoes(c)}
        usuario = json.dumps({"ficha_atual": self.ficha, "campos_pulados": sorted(self.pulados),
                              "opcoes": opcoes, "ultimas_falas": self.dialogo[-8:]}, ensure_ascii=False)
        obj, reg = self.cliente.json_por_schema(CONVERSA_SISTEMA, usuario, schema.load("conversa", SCHEMAS))
        reg["papel"] = "conversa"
        self.registros.append(reg)
        try:
            schema.validate(obj, schema.load("conversa", SCHEMAS))
        except schema.SchemaError as exc:
            reg["erro"] = f"resposta rejeitada pelo schema: {exc}"
            raise LLMIndisponivel(reg["erro"]) from exc
        for campo, valor in obj["ficha"].items():
            valor = valor.strip()
            if not valor:
                continue
            if voc.opcoes(campo):
                valor = voc.escolher(campo, valor)  # só rótulos conhecidos entram
                if not valor:
                    continue
            self.ficha[campo] = valor
        self.usou_llm = True
        if self.pendente and self.pendente not in self.ficha and voc.normalizar(texto) in PULAR:
            self.pulados.add(self.pendente)
        pergunta = obj["pergunta"].strip()
        falta = self.faltando()
        if not falta or (not pergunta and self.obrigatorios_ok()):
            return self._pronto()
        self.pendente = falta[0]
        return self._diz(pergunta or self.pergunta(falta[0]))

    def _proxima(self) -> str:
        falta = self.faltando()
        if not falta:
            return self._pronto()
        self.pendente = falta[0]
        return self._diz(self.pergunta(falta[0]))

    def _pronto(self) -> str:
        self.pendente = None
        r = modelos.montar(self.ficha, self.modelo)
        return self._diz("Pronto! Prompt montado (veja ao lado). /salvar grava em Projetos, /enviar manda "
                         "para o terminal T, /refinar reescreve com o LLM local.\n" + r["prompt"])

    def _comando(self, texto: str) -> str:
        cmd, _, arg = texto[1:].partition(" ")
        cmd = cmd.lower()
        if cmd == "pronto":
            if not self.obrigatorios_ok():
                falta = [c for c, (_, o, _) in voc.CAMPOS.items() if o and not self.ficha.get(c)]
                self.pendente = falta[0]
                return self._diz("Ainda falta o essencial. " + self.pergunta(falta[0]))
            self.pulados.update(self.faltando())
            return self._pronto()
        if cmd == "modelo":
            if arg.strip() in modelos.MODELOS:
                self.modelo = arg.strip()
                return self._diz(f"Modelo: {modelos.MODELOS[self.modelo]['nome']}.")
            return self._diz("Modelos: " + ", ".join(modelos.MODELOS))
        if cmd == "ficha":
            linhas = [f"{c}: {self.ficha.get(c, '(pulado)' if c in self.pulados else '-')}" for c in voc.ORDEM]
            return self._diz("\n".join(linhas))
        if cmd == "novo":
            self.__init__(self.modelo, self.cliente, self.modo)
            return self.abrir()
        return self._diz("Comandos: /pronto, /modelo <id>, /ficha, /novo (e na interface: /salvar, /enviar, "
                         "/refinar).")

    # ----- resultado -----
    def resultado(self, refinar: bool = False) -> Dict:
        r = modelos.montar(self.ficha, self.modelo)
        origem = "llm" if self.usou_llm else "regras"
        if refinar:
            if not self.llm_ativo:
                raise LLMIndisponivel("refino exige o LLM local (Qwen via llama-server)")
            obj, reg = self.cliente.json_por_schema(REFINO_SISTEMA, r["prompt"], schema.load("refino", SCHEMAS))
            reg["papel"] = "refino"
            self.registros.append(reg)
            schema.validate(obj, schema.load("refino", SCHEMAS))
            r["prompt"] = obj["prompt"].strip()
            origem = "llm"
        doc = {"formato": FORMATO, "criado_em": time.strftime("%Y-%m-%dT%H:%M:%S"), **r,
               "ficha": dict(self.ficha), "dialogo": list(self.dialogo), "origem": origem}
        if self.registros:
            doc["llm"] = self.registros
        schema.validate(doc, schema.load("prompt", SCHEMAS))
        return doc


def salvar(doc: Dict, pasta_projeto: str) -> str:
    """Grava em <projeto>/prompts/<data>-<modelo>.json e devolve o caminho."""
    destino = os.path.join(pasta_projeto, "prompts")
    os.makedirs(destino, exist_ok=True)
    nome = time.strftime("%Y%m%d-%H%M%S") + f"-{doc['modelo']}.json"
    caminho = os.path.join(destino, nome)
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return caminho
