"""Testes da avaliação com casos sintéticos (nenhum dado real)."""

from tratamento_pub_int.avaliar import (
    acertou,
    avaliar,
    comparar_pareado,
    comparar_rotulos,
    rotulo_de_titulo,
)
from tratamento_pub_int.relatorio import gerar_markdown, tabela_ondas


def caso(caso_id, grupo, saida, tarefas=None, reais=None, **extra):
    r = {
        "caso_id": caso_id,
        "grupo_real": grupo,
        "parsed": None if saida is None else {"saida": saida, "tarefas": tarefas or []},
        "tarefas_reais": reais or [],
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "latencia_s": 1.5,
        "finish_reason": "stop" if saida is not None else "length",
        "parse_erro": None if saida is not None else "content vazio",
    }
    r.update(extra)
    return r


FATAL15 = [{"rotulo": "[FATAL]", "acao": "Contestação", "prazo_dias": 15}]
REAL_FATAL15 = [{"titulo": "[FATAL: 20/10] Contestação", "prazo_dias": 15}]


def test_rotulo_de_titulo():
    assert rotulo_de_titulo("[FATAL: 20/10] Contestação") == "[FATAL]"
    assert rotulo_de_titulo("[diligência] Distribuir CP") == "[DILIGÊNCIA]"
    assert rotulo_de_titulo("[COMPROMISSO] Audiência") == "[COMPROMISSO]"
    assert rotulo_de_titulo("Contato com cliente") is None
    assert rotulo_de_titulo(None) is None


def test_matriz_e_metricas():
    resultados = [
        caso("A001", "tratado", "Agendamento com prazo", FATAL15, REAL_FATAL15),
        caso("A002", "tratado", "Dúvida"),  # Dúvida conta como agendar
        caso("A003", "tratado", "Nada a fazer"),  # erro caro
        caso("A004", "tratado", None),  # truncado
        caso("A005", "nada_a_fazer", "Nada a fazer"),
        caso("A006", "nada_a_fazer", "Agendamento com prazo"),
        caso("A007", "nada_a_fazer", "Dúvida"),
        caso("A008", "nada_a_fazer", "Nada a fazer"),
    ]
    av = avaliar(resultados)
    m = av.matriz
    assert (m.tratado_agendar, m.tratado_naf, m.tratado_vazio) == (2, 1, 1)
    assert (m.nada_naf, m.nada_agendar, m.nada_vazio) == (2, 2, 0)
    assert m.n == 8
    assert m.acuracia == (2 + 2) / 8
    assert m.naf_indevido == 1 / 4
    assert m.falso_agendar == 2 / 4
    assert av.parse_erros == 1
    assert av.finish_reasons == {"stop": 7, "length": 1}
    assert av.tokens_in == 8000 and av.tokens_out == 800
    assert av.latencia_media == 1.5
    assert av.custo(0.15, 0.60) == 8000 / 1e6 * 0.15 + 800 / 1e6 * 0.60


def test_rotulos_e_prazo():
    iguais, sobrepoe, prazo = comparar_rotulos(caso("x", "tratado", "Agendamento com prazo", FATAL15, REAL_FATAL15))
    assert (iguais, sobrepoe, prazo) == (True, True, True)

    reais = REAL_FATAL15 + [{"titulo": "[INTERNO] Comunicar cliente", "prazo_dias": 1}]
    previstos = [{"rotulo": "[FATAL]", "acao": "ED", "prazo_dias": 5}]
    iguais, sobrepoe, prazo = comparar_rotulos(caso("y", "tratado", "Agendamento com prazo", previstos, reais))
    assert (iguais, sobrepoe, prazo) == (False, True, False)

    # prazo ±1 bate; sem prazo real -> não comparável
    previstos14 = [{"rotulo": "[FATAL]", "acao": "Contestação", "prazo_dias": 14}]
    assert comparar_rotulos(caso("z", "tratado", "Agendamento com prazo", previstos14, REAL_FATAL15))[2] is True
    sem_prazo = [{"titulo": "[FATAL] Contestação", "prazo_dias": None}]
    assert comparar_rotulos(caso("w", "tratado", "Agendamento com prazo", FATAL15, sem_prazo))[2] is None

    # nada em comum
    comp = [{"rotulo": "[COMPROMISSO]", "acao": "Audiência", "prazo_dias": None}]
    assert comparar_rotulos(caso("v", "tratado", "Agendamento com prazo", comp, REAL_FATAL15)) == (False, False, None)


def test_avaliacao_conta_rotulos_so_nos_tratados():
    resultados = [
        caso("A001", "tratado", "Agendamento com prazo", FATAL15, REAL_FATAL15),
        caso("A002", "tratado", "Agendamento com prazo", FATAL15, [{"titulo": "[INTERNO] X", "prazo_dias": 1}]),
        caso("A003", "nada_a_fazer", "Agendamento com prazo", FATAL15, REAL_FATAL15),
    ]
    av = avaliar(resultados)
    assert av.rotulos_iguais == 1
    assert av.rotulos_sobreposicao == 1
    assert (av.prazo_bate, av.prazo_comparavel) == (1, 1)


def test_acertou_e_pareado():
    antes = [
        caso("A001", "tratado", "Agendamento com prazo"),
        caso("A002", "tratado", "Agendamento com prazo"),
        caso("A003", "nada_a_fazer", "Dúvida"),
        caso("A004", "nada_a_fazer", "Nada a fazer"),
    ]
    depois = [
        caso("A001", "tratado", "Nada a fazer"),  # certo -> errado
        caso("A002", "tratado", "Urgência"),  # certo -> certo
        caso("A003", "nada_a_fazer", "Nada a fazer"),  # errado -> certo
        caso("A004", "nada_a_fazer", None),  # certo -> errado (vazio)
    ]
    assert acertou(antes[0]) and not acertou(depois[0])
    p = comparar_pareado(antes, depois)
    assert p.n_certo_para_errado == 2
    assert p.certo_para_errado == {"tratado": 1, "nada_a_fazer": 1}
    assert p.n_errado_para_certo == 1
    assert p.certo_certo == 1 and p.errado_errado == 0


def test_relatorio_sem_ids():
    resultados = [
        caso("A001", "tratado", "Agendamento com prazo", FATAL15, REAL_FATAL15),
        caso("A002", "nada_a_fazer", "Nada a fazer"),
    ]
    av = avaliar(resultados)
    md = gerar_markdown([("piloto", av)], 0.15, 0.60, titulo="T")
    assert "| piloto | 2 | 100 % |" in tabela_ondas([("piloto", av)], 0.15, 0.60)
    assert "A001" not in md and "A002" not in md
    assert "US$ 0.0002" in md  # custo/caso: (2000*0.15 + 200*0.60)/1e6/2
