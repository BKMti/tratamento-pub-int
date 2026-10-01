# Método

## Gabarito

O gabarito é o trabalho já feito pelos analistas da Controladoria, lido do lago de dados (`forum`, só leitura). Nenhum caso foi rotulado à mão para o experimento.

- **tratado** — publicação ou intimação eletrônica do diário (`publicacao_triagem`, origem do robô de diários) marcada "Tratado" no sistema jurídico **e** com pelo menos uma tarefa rotulada pelo POP (`[FATAL`, `[PROTOCOLO`, `[COMPROMISSO`, `[INTERNO`, `[DILIG`) cadastrada no mesmo processo em até 7 dias por um dos analistas listados em `TRATAMENTO_CONTROLLERS`. As tarefas dessa janela são as "tarefas reais" do caso (rótulo + prazo em dias).
- **nada_a_fazer** — publicação marcada "Nada a fazer", com motivo preenchido nas observações do andamento (o POP exige) e **sem** tarefa rotulada em 7 dias no processo.

Limites conhecidos do gabarito: a marca "Tratado/Nada a fazer" não tem autor nem hora no lago; o vínculo tarefa ↔ publicação é "mesmo processo, até 7 dias" (não há chave direta); uma publicação pode ter sido tratada por causa de outra do mesmo dia. Concordância medida entre dois analistas humanos: 58 % na providência principal — o teto prático.

## Janelas e amostragem

| parâmetro | valor | onde |
|---|---|---|
| publicações consideradas | últimos 70 dias | `sql/amostra.sql`, `%(dias)s` |
| tarefa que define "tratado" | até 7 dias após a publicação | idem |
| texto da publicação enviado | até 3.500 caracteres | idem |
| casos por grupo | 20 (rodadas 1–2) · 50 (rodadas 3–5) | `--n` |
| sorteio | `setseed` fixo; amostra B exclui os ids da A | `--seed`, `--excluir` |
| histórico: tarefas anteriores | 60 dias antes, até 15, cadastradas ≥ 1 dia antes | `sql/historico.sql` |
| histórico: publicações anteriores | 5 mais recentes, 200 caracteres cada, com a marca de triagem | idem |
| histórico: pasta | equipe, polo do cliente, natureza, fase, ação, tipo, status | idem |

A conexão nasce com `default_transaction_read_only=on` e `statement_timeout=60s` (parâmetros de sessão); `conn.read_only = True` reforça. Os arquivos gerados em `dados/` contêm texto de publicação e ficam fora do git.

## Chamada ao modelo

- `deepseek-flash` pelo cliente OpenAI-compatível; `temperature=0`; `response_format={"type": "json_object"}`; `max_tokens=900`.
- **Raciocínio desligado**: `extra_body={"thinking": {"type": "disabled"}}`. Sem isso (rodada 1) o modelo gastou o orçamento de saída raciocinando e 31 de 40 respostas vieram vazias. Com raciocínio ligado e `max_tokens=4000` (rodada 4b) ainda truncou 7 de 20, custou 3× mais por caso, demorou 8× mais (10,9 s) e acertou menos. Para uma tarefa de classificação com tabela de regras no prompt, o raciocínio não compensa neste modelo.
- Custo estimado **antes** de qualquer chamada (pior caso: `max_tokens` cheio em todas) e comparado com o teto; contador acumulado em `dados/orcamento.json`. Erros 401/402/429 param a rodada sem tentar outra chave. A chave só aparece como `len:N`.

## Prompts

- **v1** (`prompts/system_v1.txt`): as 4 saídas do POP, a regra "na dúvida, agenda-se", os 5 rótulos e o Anexo I condensado (ato → tarefas e prazos). Saída JSON estrita. É o prompt das rodadas 1, 2, 3 e 5.
- **v2** (`prompts/system_v2.txt`): v1 + passo 0 "quem é intimado e para quê" (campo `destinatario_do_prazo`), passo 1 "use o histórico para detectar duplicidade", dois alertas de erros vistos antes, "Dúvida" restrita e seis exemplos fictícios. É o prompt das rodadas 4 e 4b. **Descartado.**

## Por que o v2 regrediu

Na mesma amostra A, o v2 trocou 22 acertos por erros e recuperou 10 (pareado caso a caso, `avaliar --pareado`):

- 21 dos 22 que pioraram eram **tratados que viraram "Nada a fazer"** — o erro caro. Em 9 deles o modelo atribuiu o prazo à "parte contrária"; em 17 disse que o comando era dirigido a "ninguém". A regra nova deu ao modelo uma justificativa pronta para descartar, e ele a usou em acórdãos desfavoráveis, sentenças homologatórias, despachos em cumprimento de sentença e migrações de sistema — todos com providência no Anexo I.
- Os 10 que melhoraram eram **nada a fazer** que o v1 mandava agendar (ou "Dúvida") e o v2 passou a descartar corretamente, quase sempre por "prazo da parte contrária" ou "mera distribuição".
- Resultado líquido: acurácia 77 → 65 %, mas o que importa é a assimetria — NAF indevido 10 → 52 % para ganhar 36 → 16 % de falso agendar. Um "Nada a fazer" errado pode custar um prazo; um agendamento a mais custa dois minutos de conferência. A troca não compensa.
- Lição: instruções que **autorizam descartar** precisam de exemplos reais e de verificação por regra fora do modelo; restringir "Dúvida" também empurrou casos para o descarte.

## Métricas (`avaliar.py`)

- Matriz 2×2 gabarito × modelo, com coluna extra para resposta vazia/truncada. "Agendar" inclui "Dúvida".
- **Acurácia** = (tratado→agendar + nada→Nada a fazer) / n.
- **NAF indevido** = tratado→Nada a fazer / tratados. **Falso agendar** = nada→agendar / nada a fazer.
- **Rótulos**: o conjunto dos rótulos reais (prefixo do título da tarefa) comparado ao conjunto previsto — iguais, ou com alguma sobreposição. **Prazo ±1**: entre rótulos em comum com prazo nos dois lados, bate se algum par difere em até 1 dia. Só medidos na rodada 2 (as rodadas 3–5 não guardaram as tarefas reais no resultado; o código atual guarda).
- Custo por caso pelos tokens reais; latência média e máxima; `finish_reason` e respostas sem JSON.

## Próximos passos (se o experimento continuar)

1. **Exemplos reais por ato do Anexo I** — para cada linha da tabela, um ou dois casos reais anonimizados (texto + pacote de tarefas que o analista criou), em vez de exemplos inventados. Os erros que restam estão concentrados em certidões, atos ordinatórios e atos sem linha na tabela.
2. **Dedupe por regra, fora da IA** — a duplicidade (publicação gêmea, tarefa já cadastrada para o mesmo evento) é detectável por comparação com o histórico, sem modelo: mesmo processo, mesmo tipo de ato, janela curta. Tirar isso do prompt simplifica a decisão do modelo e elimina a classe de erro mais perigosa (declarar "já tratado" quando há prazo novo).
3. Guardar as tarefas reais em todo resultado (já feito neste código) para medir rótulos e prazo em amostras de 100.
4. Medir contra um gabarito duplo (dois analistas) numa amostra pequena, para saber quanto do erro é do modelo e quanto é desacordo humano.
5. Uso proposto: sugestão e ordenação da fila do O Fórum (campo "sugestão da IA" + confiança), nunca marcar "Nada a fazer" sozinho.
