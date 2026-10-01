"""Chamada ao DeepSeek (cliente OpenAI-compatível), parse do JSON e contador de custo com teto.

Configuração que funcionou: raciocínio desligado (extra_body thinking disabled), max_tokens 900,
temperatura 0, response_format json_object. A chave nunca aparece em log; mensagens de erro são
sanitizadas antes de serem impressas.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Config
from .prompts import ROTULOS, SAIDAS, carregar_system, montar_mensagens

# US$ por milhão de tokens, valores usados no experimento (set./out. 2026). Confira a tabela vigente.
PRECOS_USD_POR_MILHAO: dict[str, dict[str, float]] = {
    "deepseek-flash": {"in": 0.15, "out": 0.60},
    "deepseek-chat": {"in": 0.28, "out": 0.42},
}
PRECO_PADRAO = "deepseek-chat"
MAX_TOKENS_PADRAO = 900
TEMPERATURA = 0
ERROS_FATAIS = ("401", "402", "429")  # sem chave, sem saldo, limite de taxa: parar, nunca tentar outra chave


class OrcamentoExcedido(RuntimeError):
    """A rodada pediria mais chamadas ou mais dólares do que o teto permite."""


def preco_do_modelo(modelo: str) -> dict[str, float]:
    return PRECOS_USD_POR_MILHAO.get(modelo, PRECOS_USD_POR_MILHAO[PRECO_PADRAO])


def estimar_tokens(texto: str) -> int:
    """Aproximação grosseira (~1 token a cada 3,5 caracteres em português)."""
    return max(1, int(len(texto) / 3.5))


@dataclass
class Orcamento:
    """Contador acumulado de chamadas e custo, com teto em chamadas e em US$."""

    teto_chamadas: int
    teto_usd: float
    preco_in: float
    preco_out: float
    chamadas: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    rodadas: list[dict] = field(default_factory=list)

    @classmethod
    def para(cls, cfg: Config) -> Orcamento:
        preco = preco_do_modelo(cfg.deepseek_model)
        return cls(cfg.teto_chamadas, cfg.teto_usd, preco["in"], preco["out"])

    @property
    def custo(self) -> float:
        return self.tokens_in / 1_000_000 * self.preco_in + self.tokens_out / 1_000_000 * self.preco_out

    @property
    def restante_chamadas(self) -> int:
        return self.teto_chamadas - self.chamadas

    @property
    def restante_usd(self) -> float:
        return self.teto_usd - self.custo

    def estimar(self, mensagens: list[list[dict]], max_tokens: int) -> float:
        """Pior caso: toda chamada devolve max_tokens cheio."""
        tokens_in = sum(estimar_tokens(m["content"]) for msgs in mensagens for m in msgs)
        return tokens_in / 1_000_000 * self.preco_in + len(mensagens) * max_tokens / 1_000_000 * self.preco_out

    def verificar_antes(self, mensagens: list[list[dict]], max_tokens: int) -> float:
        estimativa = self.estimar(mensagens, max_tokens)
        if len(mensagens) > self.restante_chamadas:
            raise OrcamentoExcedido(
                f"precisa de {len(mensagens)} chamadas, restam {self.restante_chamadas} do teto de {self.teto_chamadas}"
            )
        if estimativa > self.restante_usd:
            raise OrcamentoExcedido(
                f"estimativa US${estimativa:.4f} > restante US${self.restante_usd:.4f} "
                f"do teto de US${self.teto_usd:.2f}"
            )
        return estimativa

    def pode_chamar(self) -> bool:
        return self.chamadas < self.teto_chamadas and self.custo < self.teto_usd

    def registrar(self, tokens_in: int, tokens_out: int) -> None:
        self.chamadas += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def fechar_rodada(self, rotulo: str, chamadas: int, custo: float) -> None:
        self.rodadas.append({"rotulo": rotulo, "chamadas": chamadas, "custo_usd": round(custo, 4)})

    @classmethod
    def carregar(cls, caminho: Path, cfg: Config) -> Orcamento:
        orc = cls.para(cfg)
        if caminho.exists():
            estado = json.loads(caminho.read_text(encoding="utf-8"))
            orc.chamadas = int(estado.get("chamadas", 0))
            orc.tokens_in = int(estado.get("tokens_in", 0))
            orc.tokens_out = int(estado.get("tokens_out", 0))
            orc.rodadas = list(estado.get("rodadas", []))
        return orc

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        estado = asdict(self)
        estado["custo_usd"] = round(self.custo, 6)
        caminho.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_resposta(raw: str | None) -> tuple[dict | None, str | None]:
    """JSON estrito. Devolve (dict, None) ou (None, erro)."""
    if raw is None or not raw.strip():
        return None, "content vazio"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"JSON inválido: {e.msg} (pos {e.pos})"
    if not isinstance(parsed, dict):
        return None, "JSON não é objeto"
    return parsed, None


def problemas(parsed: dict) -> list[str]:
    """Checagens de forma sobre a resposta já parseada (não altera nada)."""
    lista: list[str] = []
    if parsed.get("saida") not in SAIDAS:
        lista.append(f"saida desconhecida: {parsed.get('saida')!r}")
    tarefas = parsed.get("tarefas")
    if not isinstance(tarefas, list):
        lista.append("tarefas não é lista")
        tarefas = []
    for t in tarefas:
        if not isinstance(t, dict):
            lista.append("tarefa não é objeto")
            continue
        if t.get("rotulo") not in ROTULOS:
            lista.append(f"rotulo desconhecido: {t.get('rotulo')!r}")
        prazo = t.get("prazo_dias")
        if prazo is not None and not isinstance(prazo, int):
            lista.append(f"prazo_dias não inteiro: {prazo!r}")
    if parsed.get("saida") == "Nada a fazer" and tarefas:
        lista.append("Nada a fazer com tarefas preenchidas")
    return lista


def extrair_extra(resp) -> tuple[str | None, int | None]:
    """Campos fora do schema padrão: reasoning_content e tokens de raciocínio, quando existirem."""
    try:
        d = resp.model_dump()
    except Exception:
        return None, None
    msg = d.get("choices", [{}])[0].get("message", {}) or {}
    usage = d.get("usage", {}) or {}
    reasoning_tokens = None
    detalhes = usage.get("completion_tokens_details") or {}
    if isinstance(detalhes, dict):
        reasoning_tokens = detalhes.get("reasoning_tokens")
    if reasoning_tokens is None:
        reasoning_tokens = usage.get("reasoning_tokens")
    return msg.get("reasoning_content"), reasoning_tokens


def sanitizar(texto: str, chave: str) -> str:
    return texto.replace(chave, "***CHAVE***") if chave else texto


def criar_cliente(cfg: Config):
    from openai import OpenAI

    return OpenAI(api_key=cfg.deepseek_api_key, base_url=cfg.deepseek_base_url)


def classificar_casos(
    cfg: Config,
    casos: list[dict],
    versao_prompt: str = "v1",
    max_tokens: int = MAX_TOKENS_PADRAO,
    thinking: str = "disabled",
    prefixo: str = "A",
    offset: int = 0,
    orcamento: Orcamento | None = None,
    rotulo: str = "rodada",
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Classifica os casos um a um. Para antes de estourar o teto; para em 401/402/429."""
    cfg.exigir_api()
    orcamento = orcamento or Orcamento.para(cfg)
    system_prompt = carregar_system(versao_prompt)
    mensagens = [montar_mensagens(system_prompt, caso) for caso in casos]

    log(f"{rotulo}: prompt={versao_prompt} max_tokens={max_tokens} thinking={thinking} casos={len(casos)}")
    log(f"orçamento acumulado: {orcamento.chamadas} chamadas, US${orcamento.custo:.4f}")
    estimativa = orcamento.verificar_antes(mensagens, max_tokens)
    log(f"estimativa pior caso desta rodada: US${estimativa:.4f} (dentro do teto). Prosseguindo.")

    cliente = criar_cliente(cfg)
    extra_body = {"thinking": {"type": thinking}}
    resultados: list[dict] = []
    chamadas = 0
    tokens_in = tokens_out = 0
    erro_fatal: str | None = None

    for i, (caso, msgs) in enumerate(zip(casos, mensagens, strict=True), start=1):
        if not orcamento.pode_chamar():
            log("TETO atingido. Parando.")
            break
        caso_id = f"{prefixo}{offset + i:03d}"
        t0 = time.time()
        try:
            resp = cliente.chat.completions.create(
                model=cfg.deepseek_model,
                messages=msgs,
                temperature=TEMPERATURA,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body=extra_body,
            )
        except Exception as e:
            msg = sanitizar(str(e), cfg.deepseek_api_key)
            chamadas += 1
            orcamento.registrar(0, 0)
            log(f"[{caso_id}] ERRO: {msg}")
            if any(c in msg for c in ERROS_FATAIS):
                erro_fatal = msg
                log("ERRO FATAL (401/402/429). Parando, sem tentar outra chave.")
                break
            continue
        latencia = time.time() - t0
        chamadas += 1
        raw = resp.choices[0].message.content or ""
        finish_reason = resp.choices[0].finish_reason
        pt_, ct_ = resp.usage.prompt_tokens, resp.usage.completion_tokens
        tokens_in += pt_
        tokens_out += ct_
        orcamento.registrar(pt_, ct_)
        _, reasoning_tokens = extrair_extra(resp)
        parsed, parse_erro = parse_resposta(raw)
        resultados.append(
            {
                "caso_id": caso_id,
                "grupo_real": caso["grupo"],
                "equipe": caso.get("equipe"),
                "natureza": caso.get("natureza"),
                "tarefas_reais": caso.get("tarefas"),
                "motivo_real": caso.get("motivo"),
                "raw_response": raw,
                "parsed": parsed,
                "parse_erro": parse_erro,
                "problemas": problemas(parsed) if parsed else [],
                "prompt_tokens": pt_,
                "completion_tokens": ct_,
                "reasoning_tokens": reasoning_tokens,
                "finish_reason": finish_reason,
                "latencia_s": round(latencia, 3),
            }
        )
        saida = (parsed or {}).get("saida")
        extra = f" reas_tok={reasoning_tokens}" if reasoning_tokens else ""
        log(f"[{caso_id}] saida={saida!r} fin={finish_reason} tok_in={pt_} tok_out={ct_}{extra} lat={latencia:.2f}s")

    custo = tokens_in / 1_000_000 * orcamento.preco_in + tokens_out / 1_000_000 * orcamento.preco_out
    orcamento.fechar_rodada(rotulo, chamadas, custo)
    log(
        f"chamadas={chamadas} classificados={len(resultados)} "
        f"tokens in={tokens_in} out={tokens_out} custo=US${custo:.4f}"
    )
    log(f"orçamento acumulado após a rodada: {orcamento.chamadas} chamadas, US${orcamento.custo:.4f}")
    if erro_fatal:
        log(f"PAROU POR ERRO FATAL: {erro_fatal}")
    return resultados


COLUNAS_CSV = (
    "caso_id",
    "grupo_real",
    "saida_prevista",
    "ato_previsto",
    "rotulos_previstos",
    "prazos_previstos",
    "motivo_previsto",
    "destinatario_previsto",
    "confianca",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "finish_reason",
    "latencia_s",
    "parse_erro",
)


def linha_csv(r: dict) -> list:
    p = r.get("parsed") or {}
    tarefas = [t for t in (p.get("tarefas") or []) if isinstance(t, dict)]
    return [
        r["caso_id"],
        r["grupo_real"],
        p.get("saida"),
        p.get("ato"),
        ";".join(str(t.get("rotulo", "")) for t in tarefas),
        ";".join(str(t.get("prazo_dias")) for t in tarefas),
        p.get("motivo"),
        p.get("destinatario_do_prazo"),
        p.get("confianca"),
        r.get("prompt_tokens"),
        r.get("completion_tokens"),
        r.get("reasoning_tokens"),
        r.get("finish_reason"),
        r.get("latencia_s"),
        r.get("parse_erro"),
    ]


def salvar_resultados(resultados: list[dict], caminho_json: Path) -> tuple[Path, Path]:
    """JSON completo (tem texto de publicação: fica em dados/, fora do git) e CSV resumido."""
    caminho_json.parent.mkdir(parents=True, exist_ok=True)
    caminho_json.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    caminho_csv = caminho_json.with_suffix(".csv")
    with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUNAS_CSV)
        for r in resultados:
            w.writerow(linha_csv(r))
    return caminho_json, caminho_csv


def carregar_resultados(caminho_json: Path) -> list[dict]:
    return json.loads(caminho_json.read_text(encoding="utf-8"))
