"""Testes do parse da resposta, do orçamento, dos prompts e da configuração."""

import json
from pathlib import Path

import pytest

from tratamento_pub_int import config, prompts
from tratamento_pub_int.classificar import (
    Orcamento,
    OrcamentoExcedido,
    estimar_tokens,
    linha_csv,
    parse_resposta,
    problemas,
    sanitizar,
)


def test_parse_resposta_valida():
    raw = '{"saida": "Nada a fazer", "ato": "Distribuição", "tarefas": [], "motivo": "distribuição", "confianca": 0.9}'
    parsed, erro = parse_resposta(raw)
    assert erro is None
    assert parsed["saida"] == "Nada a fazer"
    assert problemas(parsed) == []


def test_parse_resposta_vazia_e_invalida():
    assert parse_resposta("") == (None, "content vazio")
    assert parse_resposta(None) == (None, "content vazio")
    parsed, erro = parse_resposta('{"saida": "Agendamento com prazo", "tarefas": [')  # truncada
    assert parsed is None and erro.startswith("JSON inválido")
    assert parse_resposta("[1, 2]") == (None, "JSON não é objeto")


def test_problemas_de_forma():
    p = {"saida": "Talvez", "tarefas": [{"rotulo": "[URGENTE]", "prazo_dias": "cinco"}, "x"]}
    lista = problemas(p)
    assert any("saida desconhecida" in x for x in lista)
    assert any("rotulo desconhecido" in x for x in lista)
    assert any("prazo_dias não inteiro" in x for x in lista)
    assert any("tarefa não é objeto" in x for x in lista)
    assert "Nada a fazer com tarefas preenchidas" in problemas(
        {"saida": "Nada a fazer", "tarefas": [{"rotulo": "[FATAL]", "prazo_dias": 5}]}
    )
    assert "tarefas não é lista" in problemas({"saida": "Dúvida", "tarefas": None})


def test_linha_csv_resume_tarefas():
    r = {
        "caso_id": "A001",
        "grupo_real": "tratado",
        "parsed": {
            "saida": "Agendamento com prazo",
            "ato": "Citação",
            "tarefas": [{"rotulo": "[FATAL]", "prazo_dias": 15}, {"rotulo": "[INTERNO]", "prazo_dias": None}],
            "confianca": 0.9,
        },
    }
    linha = linha_csv(r)
    assert linha[:4] == ["A001", "tratado", "Agendamento com prazo", "Citação"]
    assert linha[4] == "[FATAL];[INTERNO]"
    assert linha[5] == "15;None"


def test_orcamento_tetos():
    orc = Orcamento(teto_chamadas=2, teto_usd=0.001, preco_in=0.15, preco_out=0.60)
    msgs = [[{"role": "system", "content": "a" * 350}, {"role": "user", "content": "b" * 350}]]
    # 200 tokens de entrada + 900 de saída: 200/1e6*0.15 + 900/1e6*0.60 = 0.00057 < 0.001
    assert orc.verificar_antes(msgs, 900) == pytest.approx(0.00057)
    with pytest.raises(OrcamentoExcedido, match="chamadas"):
        orc.verificar_antes(msgs * 3, 900)
    with pytest.raises(OrcamentoExcedido, match="estimativa"):
        orc.verificar_antes(msgs * 2, 900)

    assert orc.pode_chamar()
    orc.registrar(4000, 200)
    assert orc.chamadas == 1
    assert orc.custo == pytest.approx(4000 / 1e6 * 0.15 + 200 / 1e6 * 0.60)
    orc.registrar(4000, 200)
    assert not orc.pode_chamar()  # 2 chamadas = teto; custo 0.00144 > 0.001


def test_orcamento_salva_e_carrega(tmp_path: Path):
    chave_falsa = "x"
    cfg = config.Config(deepseek_api_key=chave_falsa, deepseek_model="deepseek-flash", teto_chamadas=10, teto_usd=1.0)
    orc = Orcamento.para(cfg)
    assert (orc.preco_in, orc.preco_out) == (0.15, 0.60)
    orc.registrar(1000, 100)
    orc.fechar_rodada("teste", 1, orc.custo)
    caminho = tmp_path / "orcamento.json"
    orc.salvar(caminho)
    estado = json.loads(caminho.read_text(encoding="utf-8"))
    assert estado["chamadas"] == 1 and estado["rodadas"][0]["rotulo"] == "teste"
    outro = Orcamento.carregar(caminho, cfg)
    assert (outro.chamadas, outro.tokens_in, outro.tokens_out) == (1, 1000, 100)


def test_estimar_tokens_e_sanitizar():
    assert estimar_tokens("") == 1
    assert estimar_tokens("x" * 350) == 100
    chave_falsa = "chave-falsa-123"
    assert sanitizar(f"erro com {chave_falsa} na mensagem", chave_falsa) == "erro com ***CHAVE*** na mensagem"
    assert sanitizar("sem chave", "") == "sem chave"


def test_prompts_carregam_sem_cabecalho_e_sem_nomes():
    for versao in ("v1", "v2"):
        texto = prompts.carregar_system(versao)
        assert texto.startswith("Você é um classificador")
        assert "#" not in texto.splitlines()[0]
        for saida in prompts.SAIDAS:
            assert f'"{saida}"' in texto
        for rotulo in prompts.ROTULOS:
            assert rotulo in texto
    assert "destinatario_do_prazo" in prompts.carregar_system("v2")
    assert prompts.remover_cabecalho("# a\n\n# b\ncorpo\n") == "corpo\n"


def test_montar_contexto_e_posicao():
    assert prompts.posicao_label(None) is None
    assert "polo ativo" in prompts.posicao_label("Polo ativo")
    assert "polo passivo" in prompts.posicao_label("Reclamada")
    assert prompts.posicao_label("Terceiro interessado") == "CLIENTE em posicao: Terceiro interessado"

    caso = {
        "tipo": "Publicação",
        "natureza": "Cível",
        "equipe": "Equipe X",
        "descricao": "Texto fictício da publicação.",
        "pp_posicao_cliente": "Polo passivo",
        "ve_fase": "Conhecimento",
        "tarefas_historico": [{"titulo": "[FATAL: 01/01] Contestação", "tipo": "Tarefa", "status": "Concluída"}],
        "publicacoes_anteriores": [{"trecho": "trecho", "data_evento": "2026-09-01", "subtipo_triagem": "Tratado"}],
    }
    ctx = prompts.montar_contexto(caso)
    assert ctx["texto_publicacao_atual"] == "Texto fictício da publicação."
    assert ctx["historico_processo"]["posicao_cliente"].startswith("CLIENTE no polo passivo")
    assert ctx["historico_processo"]["fase"] == "Conhecimento"
    assert ctx["tarefas_cadastradas_antes_desta_publicacao"][0]["titulo"] == "[FATAL: 01/01] Contestação"
    assert ctx["publicacoes_anteriores_do_processo"][0]["subtipo_triagem"] == "Tratado"
    msgs = prompts.montar_mensagens("SYSTEM", caso)
    assert msgs[0] == {"role": "system", "content": "SYSTEM"}
    assert json.loads(msgs[1]["content"])["tipo"] == "Publicação"


def test_config_nao_expoe_chave(tmp_path: Path, monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "FORUM_DATABASE_URL", "TRATAMENTO_CONTROLLERS", "TETO_CHAMADAS", "TETO_USD"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "DEEPSEEK_API_KEY=chave-de-teste-ficticia\n"
        "FORUM_DATABASE_URL=postgresql://usuario:senha@host:5432/forum\n"
        "TRATAMENTO_CONTROLLERS=Analista Um; Analista Dois ;\n"
        "TETO_CHAMADAS=7\nTETO_USD=0.25\n",
        encoding="utf-8",
    )
    cfg = config.carregar(env)
    assert cfg.controllers == ("Analista Um", "Analista Dois")
    assert (cfg.teto_chamadas, cfg.teto_usd) == (7, 0.25)
    descricao = cfg.descrever()
    assert "chave-de-teste-ficticia" not in descricao and "senha" not in descricao
    assert "chave-de-teste-ficticia" not in repr(cfg) and "senha" not in repr(cfg)
    assert "len:23" in descricao
    cfg.exigir_api()
    cfg.exigir_banco()
    with pytest.raises(SystemExit):
        config.Config(deepseek_api_key="").exigir_api()
    with pytest.raises(SystemExit):  # banco definido, mas sem controllers
        config.Config(
            deepseek_api_key=cfg.deepseek_api_key, forum_database_url="postgresql://host/forum"
        ).exigir_banco()
