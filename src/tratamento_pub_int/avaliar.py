"""Avaliação contra o gabarito: matriz 2×2, acurácia, erro caro, rótulos e prazo.

Convenções (iguais às do experimento):
- "agendar" = saída "Agendamento com prazo", "Urgência" ou "Dúvida" (Dúvida nunca é descarte).
- "Nada a fazer" indevido (NAF indevido) = caso tratado que o modelo mandou descartar: o erro caro.
- falso agendar = caso "nada a fazer" que o modelo mandou agendar: custa uma conferência.
- resposta vazia/truncada conta como erro nos dois grupos.
- rótulos: conjunto dos rótulos reais (prefixo do título da tarefa) x conjunto previsto; iguais ou com sobreposição.
- prazo: para rótulos em comum com prazo nos dois lados, bate se algum par diferir em até 1 dia.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .prompts import SAIDAS_QUE_AGENDAM

PREFIXOS_ROTULO = (
    ("[FATAL", "[FATAL]"),
    ("[PROTOCOLO", "[PROTOCOLO]"),
    ("[COMPROMISSO", "[COMPROMISSO]"),
    ("[INTERNO", "[INTERNO]"),
    ("[DILIG", "[DILIGÊNCIA]"),
)


def rotulo_de_titulo(titulo: str | None) -> str | None:
    """'[FATAL: 15/10] Contestação' -> '[FATAL]'."""
    if not titulo:
        return None
    t = titulo.upper()
    for prefixo, rotulo in PREFIXOS_ROTULO:
        if t.startswith(prefixo):
            return rotulo
    return None


def saida_de(resultado: dict) -> str | None:
    parsed = resultado.get("parsed") or {}
    return parsed.get("saida") or None


def manda_agendar(saida: str | None) -> bool:
    return saida in SAIDAS_QUE_AGENDAM


@dataclass
class Matriz:
    """Matriz 2×2 (mais a coluna de respostas vazias) entre gabarito e previsão."""

    tratado_agendar: int = 0
    tratado_naf: int = 0
    tratado_vazio: int = 0
    nada_naf: int = 0
    nada_agendar: int = 0
    nada_vazio: int = 0

    @property
    def n_tratado(self) -> int:
        return self.tratado_agendar + self.tratado_naf + self.tratado_vazio

    @property
    def n_nada(self) -> int:
        return self.nada_naf + self.nada_agendar + self.nada_vazio

    @property
    def n(self) -> int:
        return self.n_tratado + self.n_nada

    @property
    def acuracia(self) -> float:
        return (self.tratado_agendar + self.nada_naf) / self.n if self.n else 0.0

    @property
    def naf_indevido(self) -> float:
        return self.tratado_naf / self.n_tratado if self.n_tratado else 0.0

    @property
    def falso_agendar(self) -> float:
        return self.nada_agendar / self.n_nada if self.n_nada else 0.0


@dataclass
class Avaliacao:
    matriz: Matriz = field(default_factory=Matriz)
    saidas_tratado: Counter = field(default_factory=Counter)
    saidas_nada: Counter = field(default_factory=Counter)
    rotulos_iguais: int = 0
    rotulos_sobreposicao: int = 0
    prazo_comparavel: int = 0
    prazo_bate: int = 0
    finish_reasons: Counter = field(default_factory=Counter)
    parse_erros: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    reasoning_tokens: int = 0
    latencias: list[float] = field(default_factory=list)

    @property
    def n(self) -> int:
        return self.matriz.n

    @property
    def latencia_media(self) -> float:
        return statistics.fmean(self.latencias) if self.latencias else 0.0

    @property
    def latencia_max(self) -> float:
        return max(self.latencias) if self.latencias else 0.0

    def custo(self, preco_in: float, preco_out: float) -> float:
        return self.tokens_in / 1_000_000 * preco_in + self.tokens_out / 1_000_000 * preco_out

    def custo_por_caso(self, preco_in: float, preco_out: float) -> float:
        return self.custo(preco_in, preco_out) / self.n if self.n else 0.0


def _rotulos_reais(resultado: dict) -> dict[str, list[int | None]]:
    por_rotulo: dict[str, list[int | None]] = defaultdict(list)
    for t in resultado.get("tarefas_reais") or []:
        rot = rotulo_de_titulo((t or {}).get("titulo"))
        if rot:
            por_rotulo[rot].append(t.get("prazo_dias"))
    return por_rotulo


def _rotulos_previstos(resultado: dict) -> dict[str, list[int | None]]:
    por_rotulo: dict[str, list[int | None]] = defaultdict(list)
    for t in (resultado.get("parsed") or {}).get("tarefas") or []:
        if isinstance(t, dict) and t.get("rotulo"):
            por_rotulo[t["rotulo"]].append(t.get("prazo_dias"))
    return por_rotulo


def comparar_rotulos(resultado: dict) -> tuple[bool, bool, bool | None]:
    """(conjuntos iguais, há sobreposição, prazo bate ±1 | None se não comparável)."""
    reais = _rotulos_reais(resultado)
    previstos = _rotulos_previstos(resultado)
    set_real, set_prev = set(reais), set(previstos)
    iguais = set_real == set_prev
    sobrepoe = bool(set_real & set_prev)
    comparavel = False
    bate = False
    for rot in set_real & set_prev:
        r = [x for x in reais[rot] if x is not None]
        p = [x for x in previstos[rot] if isinstance(x, int)]
        if r and p:
            comparavel = True
            if any(abs(a - b) <= 1 for a in r for b in p):
                bate = True
    return iguais, sobrepoe, (bate if comparavel else None)


def avaliar(resultados: list[dict]) -> Avaliacao:
    av = Avaliacao()
    m = av.matriz
    for r in resultados:
        saida = saida_de(r)
        grupo = r.get("grupo_real")
        if grupo == "tratado":
            av.saidas_tratado[saida or "<vazio>"] += 1
            if saida is None:
                m.tratado_vazio += 1
            elif manda_agendar(saida):
                m.tratado_agendar += 1
            else:
                m.tratado_naf += 1
            iguais, sobrepoe, prazo = comparar_rotulos(r)
            av.rotulos_iguais += iguais
            av.rotulos_sobreposicao += sobrepoe
            if prazo is not None:
                av.prazo_comparavel += 1
                av.prazo_bate += prazo
        else:
            av.saidas_nada[saida or "<vazio>"] += 1
            if saida is None:
                m.nada_vazio += 1
            elif saida == "Nada a fazer":
                m.nada_naf += 1
            else:
                m.nada_agendar += 1
        av.finish_reasons[r.get("finish_reason") or "<n/a>"] += 1
        av.parse_erros += bool(r.get("parse_erro"))
        av.tokens_in += int(r.get("prompt_tokens") or 0)
        av.tokens_out += int(r.get("completion_tokens") or 0)
        av.reasoning_tokens += int(r.get("reasoning_tokens") or 0)
        if r.get("latencia_s") is not None:
            av.latencias.append(float(r["latencia_s"]))
    return av


def acertou(resultado: dict) -> bool:
    saida = saida_de(resultado)
    if resultado.get("grupo_real") == "tratado":
        return manda_agendar(saida)
    return saida == "Nada a fazer"


@dataclass
class Pareado:
    """Mesma amostra, duas configurações: quem mudou de lado."""

    certo_para_errado: Counter = field(default_factory=Counter)
    errado_para_certo: Counter = field(default_factory=Counter)
    certo_certo: int = 0
    errado_errado: int = 0

    @property
    def n_certo_para_errado(self) -> int:
        return sum(self.certo_para_errado.values())

    @property
    def n_errado_para_certo(self) -> int:
        return sum(self.errado_para_certo.values())


def comparar_pareado(antes: list[dict], depois: list[dict]) -> Pareado:
    por_id = {r["caso_id"]: r for r in depois}
    p = Pareado()
    for a in antes:
        b = por_id.get(a["caso_id"])
        if b is None:
            continue
        x, y = acertou(a), acertou(b)
        grupo = a.get("grupo_real", "?")
        if x and not y:
            p.certo_para_errado[grupo] += 1
        elif not x and y:
            p.errado_para_certo[grupo] += 1
        elif x and y:
            p.certo_certo += 1
        else:
            p.errado_errado += 1
    return p
