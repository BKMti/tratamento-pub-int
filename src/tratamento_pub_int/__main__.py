"""Linha de comando: amostra | classificar | avaliar | relatorio.

uv run python -m tratamento_pub_int amostra      --n 50 --dias 70 --seed 0.42
uv run python -m tratamento_pub_int classificar  --prompt v1 --rotulo piloto3
uv run python -m tratamento_pub_int avaliar      dados/resultados_piloto3.json [--pareado dados/resultados_x.json]
uv run python -m tratamento_pub_int relatorio    dados/resultados_*.json --saida dados/relatorio.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import amostra as mod_amostra
from . import avaliar as mod_avaliar
from . import classificar as mod_classificar
from . import config as mod_config
from . import relatorio as mod_relatorio


def cmd_amostra(args: argparse.Namespace) -> int:
    cfg = mod_config.carregar()
    cfg.exigir_banco()
    print(cfg.descrever())
    excluir: list[int] = []
    for caminho in args.excluir:
        excluir += mod_amostra.ids_de(mod_amostra.carregar_amostra(Path(caminho)))
    with mod_amostra.abrir_conexao(cfg) as conn:
        casos = mod_amostra.extrair_amostra(conn, cfg.controllers, args.n, args.dias, args.seed, excluir)
        if not args.sem_historico:
            mod_amostra.enriquecer_historico(conn, casos)
    saida = Path(args.saida) if args.saida else cfg.dados_dir / "amostra.json"
    mod_amostra.salvar_amostra(casos, saida)
    grupos = {g: sum(1 for c in casos if c["grupo"] == g) for g in ("tratado", "nada_a_fazer")}
    print(f"{len(casos)} casos {grupos} -> {saida}")
    print("AVISO: o arquivo tem texto de publicação (dado de produção). Fica em dados/, fora do git. Apague ao final.")
    return 0


def cmd_classificar(args: argparse.Namespace) -> int:
    cfg = mod_config.carregar()
    cfg.exigir_api()
    print(cfg.descrever())
    amostra_path = Path(args.amostra) if args.amostra else cfg.dados_dir / "amostra.json"
    casos = mod_amostra.carregar_amostra(amostra_path)[args.offset : args.offset + args.limite]
    orcamento_path = cfg.dados_dir / "orcamento.json"
    orcamento = mod_classificar.Orcamento.carregar(orcamento_path, cfg)
    try:
        resultados = mod_classificar.classificar_casos(
            cfg, casos, args.prompt, args.max_tokens, args.thinking, args.prefixo, args.offset, orcamento, args.rotulo
        )
    except mod_classificar.OrcamentoExcedido as e:
        print(f"ABORTADO antes de qualquer chamada: {e}")
        return 1
    finally:
        orcamento.salvar(orcamento_path)
    saida = cfg.dados_dir / f"resultados_{args.rotulo}.json"
    js, csv_ = mod_classificar.salvar_resultados(resultados, saida)
    print(f"JSON completo: {js}\nCSV resumido: {csv_}")
    av = mod_avaliar.avaliar(resultados)
    print(mod_relatorio.detalhe_markdown(args.rotulo, av, orcamento.preco_in, orcamento.preco_out))
    return 0


def _preco() -> tuple[float, float]:
    cfg = mod_config.carregar()
    p = mod_classificar.preco_do_modelo(cfg.deepseek_model)
    return p["in"], p["out"]


def cmd_avaliar(args: argparse.Namespace) -> int:
    preco_in, preco_out = _preco()
    resultados = mod_classificar.carregar_resultados(Path(args.resultados))
    av = mod_avaliar.avaliar(resultados)
    print(mod_relatorio.detalhe_markdown(Path(args.resultados).stem, av, preco_in, preco_out))
    if args.pareado:
        depois = mod_classificar.carregar_resultados(Path(args.pareado))
        p = mod_avaliar.comparar_pareado(resultados, depois)
        print(mod_relatorio.pareado_markdown(Path(args.resultados).stem, Path(args.pareado).stem, p))
    return 0


def cmd_relatorio(args: argparse.Namespace) -> int:
    preco_in, preco_out = _preco()
    ondas = []
    for caminho in args.resultados:
        p = Path(caminho)
        ondas.append((p.stem.removeprefix("resultados_"), mod_avaliar.avaliar(mod_classificar.carregar_resultados(p))))
    texto = mod_relatorio.gerar_markdown(ondas, preco_in, preco_out, titulo=args.titulo)
    if args.saida:
        Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_text(texto, encoding="utf-8")
        print(f"relatório: {args.saida}")
    else:
        print(texto)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="tratamento_pub_int", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("amostra", help="extrai a amostra rotulada do banco forum (só leitura)")
    a.add_argument("--n", type=int, default=50, help="casos por grupo (padrão 50)")
    a.add_argument("--dias", type=int, default=70, help="janela para trás em dias (padrão 70)")
    a.add_argument("--seed", type=float, default=0.42, help="semente do sorteio (padrão 0.42)")
    a.add_argument("--excluir", action="append", default=[], help="amostra anterior cujos ids não podem repetir")
    a.add_argument("--sem-historico", action="store_true", help="não buscar o histórico do processo")
    a.add_argument("--saida", help="arquivo JSON de saída (padrão dados/amostra.json)")
    a.set_defaults(func=cmd_amostra)

    c = sub.add_parser("classificar", help="chama o DeepSeek para cada caso da amostra")
    c.add_argument("--amostra", help="JSON gerado por `amostra` (padrão dados/amostra.json)")
    c.add_argument("--prompt", default="v1", choices=["v1", "v2"])
    c.add_argument("--max-tokens", type=int, default=mod_classificar.MAX_TOKENS_PADRAO)
    c.add_argument("--thinking", default="disabled", choices=["disabled", "enabled"])
    c.add_argument("--limite", type=int, default=100)
    c.add_argument("--offset", type=int, default=0)
    c.add_argument("--prefixo", default="A", help="prefixo do caso_id (A, B...)")
    c.add_argument("--rotulo", default="rodada", help="nome da rodada; vira dados/resultados_<rotulo>.json")
    c.set_defaults(func=cmd_classificar)

    v = sub.add_parser("avaliar", help="matriz 2×2 e métricas de um resultado")
    v.add_argument("resultados", help="dados/resultados_<rotulo>.json")
    v.add_argument("--pareado", help="segundo resultado da mesma amostra para comparar caso a caso")
    v.set_defaults(func=cmd_avaliar)

    r = sub.add_parser("relatorio", help="markdown agregado de várias rodadas (sem ids)")
    r.add_argument("resultados", nargs="+")
    r.add_argument("--saida", help="arquivo .md; sem ele, imprime")
    r.add_argument("--titulo", default="Resultados")
    r.set_defaults(func=cmd_relatorio)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
