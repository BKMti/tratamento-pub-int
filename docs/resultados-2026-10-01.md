# Resultados — 30/09 a 01/10/2026

Modelo `deepseek-flash`, temperatura 0, `response_format` JSON, preço usado US$ 0,15/M entrada e US$ 0,60/M saída (informado à época; raciocínio cobrado como saída). Total: **400 chamadas, US$ 0,33**. Grau de certeza: ✔ medido, ◐ inferido.

Convenções: "agendar" = Agendamento com prazo, Urgência ou Dúvida. **NAF indevido** = caso tratado que o modelo mandou descartar (o erro caro: risco de perda de prazo). **Falso agendar** = caso "nada a fazer" que o modelo mandou agendar (custa uma conferência). Resposta vazia/truncada conta como erro.

## Visão geral

| rodada | configuração | n | acurácia | NAF indevido | falso agendar | rótulos iguais | sobreposição | prazo ±1 | custo/caso | latência média |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | v1, sem histórico, max_tokens 600, raciocínio padrão | 40 | 12 % (31 truncadas) | 0/20 | 4/20 | — | — | — | US$ 0,0008 | 3,3 s |
| 2 | v1, sem histórico, raciocínio **desligado**, max_tokens 900 | 40 | 65 % | 5 % (1/20) | 65 % (13/20) | 35 % (7/20) | 70 % (14/20) | 3/7 | US$ 0,0006 | 1,4 s |
| 3 | v1 + **histórico**, raciocínio desligado — amostra A | 100 | **77 %** | **10 %** (5/50) | 36 % (18/50) | n/m | n/m | n/m | US$ 0,0007 | 1,4 s |
| 4 | v2 + histórico, raciocínio desligado — amostra A | 100 | 65 % | **52 %** (26/50) | 16 % (8/50) | n/m | n/m | n/m | US$ 0,0009 | 1,3 s |
| 4b | v2 + histórico, raciocínio **ligado**, max_tokens 4000 — 20 tratados de A | 20 | 40 % (7 truncadas) | 25 % (5/20) | — | n/m | n/m | n/m | US$ 0,0023 | 10,9 s |
| 5 | = rodada 3 — amostra B nova | 100 | **77 %** | **10 %** (5/50) | 36 % (18/50) | n/m | n/m | n/m | US$ 0,0007 | 1,4 s |

n/m = não medido nessas rodadas (rótulos e prazo só foram conferidos na rodada 2; a comparação de rótulos exige a lista de tarefas reais, que só ficou guardada nesse piloto).

## Rodada 1 — v1, max_tokens 600, raciocínio padrão ✔

| gabarito \ modelo | agendar | Nada a fazer | vazio/truncado |
|---|---|---|---|
| tratado (20) | 3 | 0 | 17 |
| nada a fazer (20) | 4 | 2 | 14 |

- 31 de 40 respostas vieram vazias: o modelo gastou o orçamento de saída "pensando" (raciocínio interno) e não sobrou token para o JSON.
- Tokens: entrada 133.584, saída 21.747; custo US$ 0,0331. Latência média 3,3 s.
- Lição: com este modelo, raciocínio precisa ser desligado explicitamente (`extra_body={"thinking": {"type": "disabled"}}`).

## Rodada 2 — v1, raciocínio desligado, max_tokens 900 ✔

| gabarito \ modelo | agendar | Nada a fazer | vazio/truncado |
|---|---|---|---|
| tratado (20) | 19 (14 Agendamento, 5 Dúvida) | **1** | 0 |
| nada a fazer (20) | 13 (5 Agendamento, 8 Dúvida) | 7 | 0 |

- 40/40 JSON válido. Acurácia 65 %. O único NAF indevido: aviso de migração de sistema que escondia um prazo de 9 dias.
- Falso agendar 65 %: quase tudo "Dúvida" — o modelo segue "na dúvida, agenda-se" demais.
- Rótulos (20 tratados): conjunto igual em 7, alguma sobreposição em 14. Prazo ±1 dia: 3 de 7 comparáveis.
- Tokens: entrada 132.584, saída 4.535; custo US$ 0,0226 (US$ 0,0006/caso; ≈ US$ 1,9/mês para 3.300 publicações). Latência 1,4 s.
- Erros reprodutíveis: perícia designada lida como "esclarecimento do perito"; recria o pacote de tarefas de uma audiência já agendada (sem histórico do processo não tem como saber).

## Rodada 3 — v1 + histórico do processo, raciocínio desligado, amostra A ✔

| gabarito \ modelo | agendar | Nada a fazer | vazio/truncado |
|---|---|---|---|
| tratado (50) | 45 (41 Agendamento, 4 Dúvida) | **5** | 0 |
| nada a fazer (50) | 18 (11 Agendamento, 7 Dúvida) | 32 | 0 |

- Acurácia 77 %; NAF indevido 10 %; falso agendar 36 %. Confiança média declarada 0,84.
- Histórico enviado: dados cadastrais da pasta (equipe, polo do cliente, natureza, fase, ação, tipo, status), até 15 tarefas cadastradas nos 60 dias anteriores e as 5 publicações anteriores do processo (200 caracteres cada).
- Rótulos previstos nos agendamentos: [FATAL] 62, [INTERNO] 52, [COMPROMISSO] 9, [PROTOCOLO] 9, [DILIGÊNCIA] 0.
- Tokens: entrada 412.404, saída 12.232; custo US$ 0,0692. Latência 1,4 s (máx. 2,1 s).
- Os 5 NAF indevidos (descritos genericamente): certidão de trânsito em julgado com remessa ao arquivo (o POP pede [INTERNO] verificar arquivamento/comunicar); juntada de certidão lida como "sem efeito intimatório"; ato ordinatório de expedição de certidão; comunicação sobre carta precatória tratada como informativa; decisão de cancelamento de distribuição de recurso em duplicidade. Padrão: **providência interna escondida em certidão/ato ordinatório**.

## Rodada 4 — v2 + histórico, raciocínio desligado, amostra A ✔

| gabarito \ modelo | agendar | Nada a fazer | vazio/truncado |
|---|---|---|---|
| tratado (50) | 24 | **26** | 0 |
| nada a fazer (50) | 8 (5 Agendamento, 3 Dúvida) | 41 | 1 |

- Acurácia 65 %; NAF indevido **52 %**; falso agendar 16 %. O v2 trocou o erro barato pelo erro caro.
- Motivo "prazo da parte contrária" apareceu em 27 dos 67 "Nada a fazer" — em 9 casos tratados. Em outros 17 tratados o modelo disse que o destinatário era "ninguém" (acórdão desfavorável, sentença homologatória, despacho em cumprimento de sentença, trânsito em julgado, migração de sistema...).
- Pareado com a rodada 3 (mesma amostra): **22 casos certo → errado** (21 tratados, 1 nada a fazer) contra **10 errado → certo** (todos nada a fazer); 55 certos nos dois, 13 errados nos dois.
- Prompt 36 % maior (entrada 568.804 tokens); custo US$ 0,0911. Latência 1,3 s.

## Rodada 4b — v2 + raciocínio ligado, 20 tratados da amostra A ✔

- 13 respostas completas, 7 truncadas mesmo com max_tokens 4000 (`finish_reason=length`). Dos 20: 8 agendar, 5 Nada a fazer, 7 vazias → acurácia 40 %, NAF indevido 25 %.
- Raciocínio: 45.827 tokens (média 2.291 por caso), cobrados como saída. Custo US$ 0,0462 (US$ 0,0023/caso, 3× o da rodada 3). Latência média 10,9 s (máx. 19,8 s).
- Conclusão: pior, mais caro e mais lento. Descartado.

## Rodada 5 — configuração da rodada 3, amostra B nova ✔

| gabarito \ modelo | agendar | Nada a fazer | vazio/truncado |
|---|---|---|---|
| tratado (50) | 45 (37 Agendamento, 8 Dúvida) | **5** | 0 |
| nada a fazer (50) | 18 (13 Agendamento, 5 Dúvida) | 32 | 0 |

- Mesmos 77 % / 10 % / 36 % da amostra A: o resultado se repete em amostra independente (sem sobreposição de casos). Confiança média 0,82.
- Rótulos previstos: [FATAL] 54, [INTERNO] 52, [COMPROMISSO] 4, [PROTOCOLO] 4.
- Tokens: entrada 413.572, saída 12.120; custo US$ 0,0693. Latência 1,4 s.
- Os 5 NAF indevidos: juntada de petição de embargos de declaração lida como "já tratada" (havia prazo real de 4 dias — **o caso mais grave**); juntada de certidão; distribuição de carta precatória (o POP pede [FATAL] comprovar distribuição + [DILIGÊNCIA]); sentença de extinção sem resolução de mérito (o POP pede [INTERNO] comunicar/verificar arquivamento); decisão monocrática de não conhecimento de agravo (abre prazo de agravo interno).

## Erros que restam (rodadas 3 e 5) ◐

1. **Certidões e atos ordinatórios com providência interna escondida** — o modelo lê "mera certidão" e descarta; o POP quase sempre pede ao menos um [INTERNO].
2. **Duplicidade** — mesmo vendo no histórico uma tarefa igual, às vezes recria o pacote; outras vezes declara "já tratado" quando a publicação nova abre prazo próprio.
3. **Atos fora do Anexo I** (ex.: habilitação em falência) — não há linha na tabela; o modelo improvisa.
4. **"Dúvida" como escape** — 4 a 8 % dos tratados e 10 a 14 % dos nada a fazer; não é descarte, mas também não ordena a fila.

## Referência humana ◐

Em sessão anterior, dois analistas humanos concordaram em 58 % na providência principal e em 50 % no prazo (±1 dia útil) sobre a mesma amostra. Qualquer medida de "acerto" do modelo tem esse teto como referência: 77 % contra um gabarito feito por um só analista não é comparável a 100 %.
