"""Camada A3 da carteira própria: agentes analistas em papel (ADR 0118, Emenda 1, item 8).

- `criterios`: os números do texto `docs/criterios-agentes-analistas-v0.1.md` e a trava do hash
  (o texto é do Tiago; sem o hash aprovado nada roda);
- `rodada`: o universo mecânico, o pedido fixo de cada agente, a leitura da nota e a regra que monta
  a carteira; prepara e registra a rodada do mês;
- `registro`: a cadeia de hashes (uma linha por rodada, nada se edita) e os dossiês pelo hash;
- `comparacao`: a nota contra o preço 12 meses depois e a carteira em papel com custo e freio.

Os agentes rodam numa sessão local do Claude Code (subagentes Sonnet, pela assinatura): este pacote
não chama nenhuma API, não envia ordem e não lê dado pessoal do Tiago.
"""
