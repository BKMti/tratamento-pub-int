"""Extração da amostra rotulada e do histórico do processo no banco `forum`. SÓ LEITURA.

A conexão nasce com default_transaction_read_only=on e statement_timeout; nenhuma função aqui escreve.
Os arquivos gerados contêm texto de publicação (dado de produção) e ficam em dados/, fora do git.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .config import Config, raiz_projeto

SQL_DIR = raiz_projeto() / "sql"
STATEMENT_TIMEOUT_MS = 60_000


def ler_sql(nome: str) -> str:
    return (SQL_DIR / nome).read_text(encoding="utf-8")


def abrir_conexao(cfg: Config) -> psycopg.Connection:
    """Abre a conexão só leitura, com timeout por comando, já no nível da sessão."""
    conn = psycopg.connect(
        cfg.forum_database_url,
        options=f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}",
        application_name="tratamento-pub-int",
        row_factory=dict_row,
    )
    conn.read_only = True
    return conn


def extrair_amostra(
    conn: psycopg.Connection,
    controllers: Sequence[str],
    n_por_grupo: int = 50,
    dias: int = 70,
    seed: float = 0.42,
    excluir: Iterable[int] = (),
) -> list[dict]:
    """n_por_grupo casos 'tratado' + n_por_grupo 'nada_a_fazer', sorteados com semente fixa."""
    with conn.cursor() as cur:
        cur.execute("SELECT setseed(%(seed)s)", {"seed": seed})
        cur.execute(
            ler_sql("amostra.sql"),
            {
                "controllers": list(controllers),
                "dias": dias,
                "limite": n_por_grupo,
                "excluir": [int(x) for x in excluir],
            },
        )
        casos = [dict(linha) for linha in cur.fetchall()]
    conn.rollback()
    return casos


def enriquecer_historico(
    conn: psycopg.Connection,
    casos: list[dict],
    dias_hist: int = 60,
    tarefas_max: int = 15,
    pubs_max: int = 5,
) -> list[dict]:
    """Acrescenta a cada caso os campos pp_*, ve_*, tarefas_historico e publicacoes_anteriores."""
    sql = ler_sql("historico.sql")
    with conn.cursor() as cur:
        for caso in casos:
            cur.execute(
                sql,
                {
                    "processo_id": caso["processo_id"],
                    "data_evento": caso["data_evento"],
                    "dias_hist": dias_hist,
                    "tarefas_max": tarefas_max,
                    "pubs_max": pubs_max,
                },
            )
            linha = cur.fetchone()
            if linha:
                caso.update(dict(linha))
    conn.rollback()
    return casos


def _serializar(valor):
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    raise TypeError(f"tipo não serializável: {type(valor).__name__}")


def salvar_amostra(casos: list[dict], caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(casos, ensure_ascii=False, indent=1, default=_serializar), encoding="utf-8")
    return caminho


def carregar_amostra(caminho: Path) -> list[dict]:
    return json.loads(caminho.read_text(encoding="utf-8"))


def ids_de(casos: Iterable[dict]) -> list[int]:
    return [int(c["andamento_id"]) for c in casos if c.get("andamento_id") is not None]
