"""Prompts do sistema e montagem do contexto enviado ao modelo."""

from __future__ import annotations

import json
from pathlib import Path

from .config import raiz_projeto

SAIDAS = ("Agendamento com prazo", "Urgência", "Nada a fazer", "Dúvida")
SAIDAS_QUE_AGENDAM = frozenset({"Agendamento com prazo", "Urgência", "Dúvida"})
ROTULOS = ("[FATAL]", "[PROTOCOLO]", "[COMPROMISSO]", "[INTERNO]", "[DILIGÊNCIA]")


def caminho_prompt(versao: str) -> Path:
    return raiz_projeto() / "prompts" / f"system_{versao}.txt"


def carregar_system(versao: str = "v1") -> str:
    """Lê prompts/system_<versao>.txt. Linhas iniciais começadas por '#' são cabeçalho e não vão ao modelo."""
    texto = caminho_prompt(versao).read_text(encoding="utf-8")
    return remover_cabecalho(texto)


def remover_cabecalho(texto: str) -> str:
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas) and (linhas[i].startswith("#") or not linhas[i].strip()):
        i += 1
    return "\n".join(linhas[i:]).strip() + "\n"


def posicao_label(posicao: str | None) -> str | None:
    """Traduz a posição do cliente na pasta para uma frase que o modelo entende."""
    if not posicao:
        return None
    p = posicao.lower()
    if "ativ" in p or "autor" in p or "reclamante" in p:
        return "CLIENTE no polo ativo (autor/requerente/reclamante)"
    if "passiv" in p or "reclamada" in p or "ré" in p:
        return "CLIENTE no polo passivo (réu/requerido/reclamada)"
    return f"CLIENTE em posicao: {posicao}"


def montar_contexto(caso: dict) -> dict:
    """Monta o JSON do usuário: dados da pasta, tarefas anteriores, publicações anteriores e o texto atual."""
    processo = {
        "equipe": caso.get("pp_equipe") or caso.get("equipe"),
        "posicao_cliente": posicao_label(caso.get("pp_posicao_cliente")),
        "natureza": caso.get("ve_natureza") or caso.get("natureza"),
        "fase": caso.get("ve_fase"),
        "acao": caso.get("ve_acao"),
        "tipo_processo": caso.get("ve_tipo_processo"),
        "status": caso.get("ve_status"),
    }
    tarefas_hist = [
        {
            "titulo": t.get("titulo"),
            "tipo": t.get("tipo"),
            "subtipo": t.get("subtipo"),
            "status": t.get("status"),
            "data_inicio": t.get("data_inicio"),
            "data_fim": t.get("data_fim"),
        }
        for t in (caso.get("tarefas_historico") or [])
    ]
    pubs_ant = [
        {
            "trecho": p.get("trecho"),
            "data_evento": p.get("data_evento"),
            "subtipo_triagem": p.get("subtipo_triagem"),
        }
        for p in (caso.get("publicacoes_anteriores") or [])
    ]
    return {
        "tipo": caso["tipo"],
        "natureza": caso.get("natureza"),
        "equipe": caso.get("equipe"),
        "historico_processo": processo,
        "tarefas_cadastradas_antes_desta_publicacao": tarefas_hist,
        "publicacoes_anteriores_do_processo": pubs_ant,
        "texto_publicacao_atual": caso["descricao"],
    }


def montar_mensagens(system_prompt: str, caso: dict) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(montar_contexto(caso), ensure_ascii=False)},
    ]
