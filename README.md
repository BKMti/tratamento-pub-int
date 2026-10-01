# tratamento-pub-int

Experimento: um modelo de linguagem barato (DeepSeek, `deepseek-flash`) lendo publicações e intimações judiciais e decidindo, como faria um analista da Controladoria de um escritório de advocacia, a providência prevista no POP de tratamento de intimações e publicações — agendar com prazo, urgência, nada a fazer ou dúvida — e quais tarefas rotuladas (`[FATAL]`, `[PROTOCOLO]`, `[COMPROMISSO]`, `[INTERNO]`, `[DILIGÊNCIA]`) o ato gera.

**Estado: experimento concluído em 01/10/2026. No servidor fica inativo** — nada roda sozinho; ver `ESTADO.md`.

## Relação com o projeto irmão

No O Fórum (plataforma interna do escritório) existe o painel **KPI de publicações**, que **mede** o tratamento feito pelas pessoas: volume por equipe, tarefas por analista, aderência ao POP (rótulo, motivo do "nada a fazer", prazo, tempo até a tarefa). Este repositório é o outro lado da mesma pergunta: se o tratamento pode ser **sugerido por IA**. O KPI mede; este classifica. O resultado do experimento aparece no painel só como texto (bloco "Classificação por IA"); não há chamada ao vivo.

## O que foi medido

Cinco rodadas em 30/09–01/10/2026, 400 chamadas, US$ 0,33 no total. Gabarito: publicações já tratadas pelos analistas (detalhes em `docs/metodo.md`).

| rodada | configuração | n | acurácia | "Nada a fazer" indevido | falso agendar | custo/caso |
|---|---|---|---|---|---|---|
| 1 | v1, max_tokens 600, raciocínio padrão | 40 | 31/40 truncadas | — | — | US$ 0,0008 |
| 2 | v1, raciocínio desligado, max_tokens 900 | 40 | 65 % | 5 % (1/20) | 65 % | US$ 0,0006 |
| 3 | v1 + **histórico do processo**, raciocínio desligado (amostra A) | 100 | **77 %** | **10 %** (5/50) | 36 % | US$ 0,0007 |
| 4 | v2 (regra "prazo da parte contrária", exemplos, duas etapas), amostra A | 100 | 65 % | 52 % (26/50) | 16 % | US$ 0,0009 |
| 4b | v2 + raciocínio ligado (20 tratados) | 20 | 40 %, 7/20 truncadas | 25 % | — | US$ 0,0023 |
| 5 | = rodada 3, amostra B nova | 100 | **77 %** | **10 %** (5/50) | 36 % | US$ 0,0007 |

Leitura: o histórico do processo foi o que mais ajudou (65 → 77 %); o prompt v2 regrediu no erro caro; raciocínio ligado é pior, mais caro e mais lento. Serve como **segunda opinião e ordenação da fila**; não para marcar "nada a fazer" sozinho. Números completos, matrizes e erros típicos em `docs/resultados-2026-10-01.md`.

## Como rodar

Python 3.12 e [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.exemplo .env     # preencher DEEPSEEK_API_KEY, FORUM_DATABASE_URL e TRATAMENTO_CONTROLLERS
uv run python -m tratamento_pub_int amostra      --n 50 --dias 70 --seed 0.42
uv run python -m tratamento_pub_int classificar  --prompt v1 --rotulo piloto3 --prefixo A
uv run python -m tratamento_pub_int avaliar      dados/resultados_piloto3.json
uv run python -m tratamento_pub_int relatorio    dados/resultados_*.json --saida dados/relatorio.md
```

- `amostra` lê o banco `forum` **SÓ LEITURA** (a conexão abre com `default_transaction_read_only=on` e `statement_timeout`) e grava a amostra em `dados/` — que tem texto de publicação e **fica fora do git**. Apague ao final.
- `classificar` estima o custo **antes** de qualquer chamada e para quando bate o teto (`TETO_CHAMADAS`, `TETO_USD`); o acumulado fica em `dados/orcamento.json`. Para em 401/402/429 sem tentar outra chave. A chave nunca aparece em log.
- `avaliar` imprime a matriz 2×2 e as métricas; `--pareado` compara duas rodadas da mesma amostra caso a caso.
- `relatorio` gera o markdown agregado (só números, nenhum id).

Testes e lint: `uv run pytest` e `uv run ruff check .`.

## Estrutura

```
src/tratamento_pub_int/   config · amostra · prompts · classificar · avaliar · relatorio · __main__
prompts/                  system_v1.txt (recomendado) · system_v2.txt (descartado, mantido como registro)
sql/                      amostra.sql · historico.sql (parametrizados, só leitura)
docs/                     resultados-2026-10-01.md · metodo.md
tests/                    test_avaliar.py · test_parser.py
```

## Licença

A decidir pelo dono do repositório. Até lá, todos os direitos reservados.
