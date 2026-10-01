"""Relatório agregado em markdown. Só números: nenhum id, nenhum texto de publicação."""

from __future__ import annotations

from .avaliar import Avaliacao, Pareado


def pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def tabela_ondas(ondas: list[tuple[str, Avaliacao]], preco_in: float, preco_out: float) -> str:
    cab = (
        "| rodada | n | acurácia | NAF indevido | falso agendar | rótulos iguais | sobreposição | prazo ±1 | "
        "custo/caso | latência média |\n|---|---|---|---|---|---|---|---|---|---|\n"
    )
    linhas = []
    for rotulo, av in ondas:
        m = av.matriz
        nt = m.n_tratado or 1
        prazo = f"{av.prazo_bate}/{av.prazo_comparavel}" if av.prazo_comparavel else "—"
        linhas.append(
            f"| {rotulo} | {av.n} | {pct(m.acuracia)} | {pct(m.naf_indevido)} ({m.tratado_naf}/{m.n_tratado}) | "
            f"{pct(m.falso_agendar)} ({m.nada_agendar}/{m.n_nada}) | {av.rotulos_iguais}/{nt} | "
            f"{av.rotulos_sobreposicao}/{nt} | {prazo} | US$ {av.custo_por_caso(preco_in, preco_out):.4f} | "
            f"{av.latencia_media:.1f} s |"
        )
    return cab + "\n".join(linhas) + "\n"


def matriz_markdown(av: Avaliacao) -> str:
    m = av.matriz
    return (
        "| gabarito \\ modelo | agendar (inclui Dúvida) | Nada a fazer | vazio/truncado |\n|---|---|---|---|\n"
        f"| tratado ({m.n_tratado}) | {m.tratado_agendar} | **{m.tratado_naf}** | {m.tratado_vazio} |\n"
        f"| nada a fazer ({m.n_nada}) | {m.nada_agendar} | {m.nada_naf} | {m.nada_vazio} |\n"
    )


def detalhe_markdown(rotulo: str, av: Avaliacao, preco_in: float, preco_out: float) -> str:
    raciocinio = f", raciocínio {milhar(av.reasoning_tokens)}" if av.reasoning_tokens else ""
    return (
        f"### {rotulo}\n\n"
        + matriz_markdown(av)
        + f"\n- saídas nos tratados: {dict(av.saidas_tratado)}; nos nada a fazer: {dict(av.saidas_nada)}\n"
        f"- finish_reason: {dict(av.finish_reasons)}; respostas sem JSON: {av.parse_erros}\n"
        f"- tokens: entrada {milhar(av.tokens_in)}, saída {milhar(av.tokens_out)}{raciocinio}; "
        f"custo US$ {av.custo(preco_in, preco_out):.4f} (US$ {av.custo_por_caso(preco_in, preco_out):.4f}/caso)\n"
        f"- latência média {av.latencia_media:.1f} s, máxima {av.latencia_max:.1f} s\n"
    )


def pareado_markdown(rotulo_a: str, rotulo_b: str, p: Pareado) -> str:
    return (
        f"### Pareado: {rotulo_a} -> {rotulo_b}\n\n"
        f"- certo -> errado: **{p.n_certo_para_errado}** {dict(p.certo_para_errado)}\n"
        f"- errado -> certo: **{p.n_errado_para_certo}** {dict(p.errado_para_certo)}\n"
        f"- certo nos dois: {p.certo_certo}; errado nos dois: {p.errado_errado}\n"
    )


def gerar_markdown(
    ondas: list[tuple[str, Avaliacao]],
    preco_in: float,
    preco_out: float,
    pareados: list[tuple[str, str, Pareado]] | None = None,
    titulo: str = "Resultados",
) -> str:
    partes = [f"# {titulo}\n\n", tabela_ondas(ondas, preco_in, preco_out), "\n"]
    for rotulo, av in ondas:
        partes.append(detalhe_markdown(rotulo, av, preco_in, preco_out))
        partes.append("\n")
    for a, b, p in pareados or []:
        partes.append(pareado_markdown(a, b, p))
        partes.append("\n")
    return "".join(partes)
