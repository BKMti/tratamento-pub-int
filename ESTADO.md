# Estado

**Experimento concluído em 01/10/2026.** No servidor fica inativo: não há serviço, timer nem chamada ao vivo; o classificador roda só à mão, a partir de uma estação com acesso de leitura ao banco `forum` e uma chave do DeepSeek.

Para rodar de novo:

```
uv sync
cp .env.exemplo .env      # preencher chave, URL do banco e TRATAMENTO_CONTROLLERS
uv run python -m tratamento_pub_int amostra
uv run python -m tratamento_pub_int classificar
uv run python -m tratamento_pub_int avaliar
```

Resultado da última rodada: `docs/resultados-2026-10-01.md`. Configuração recomendada: prompt v1 + histórico do processo, raciocínio desligado — como **sugestão e ordenação da fila**, nunca para marcar "Nada a fazer" sozinho.
