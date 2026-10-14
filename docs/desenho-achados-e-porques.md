# Evidências e porquês: como os modelos conversam no relatório

**Situação:** proposta de 14/10/2026; decisões do Tiago na seção 10. Etapa 1 em construção (seção 9).
Vira uma ADR na pasta privada, e cada etapa da seção 9 vira um PR.

**Nome:** a proposta chamava a peça de "achado"; no código ela é **evidência** (`src/evidencias.py`),
porque achado já é o problema de qualidade de dados (`base/regras.py`, o selo de qualidade).

## 1. O que o Tiago pediu

Que os modelos (macroeconômicos, técnicos, fundamentalistas e quantitativos) **se integrem na hora de
gerar o relatório**, com **vários porquês e as respostas de cada porquê**, e que isso seja algo que os
modelos aprendam a fazer.

Em uma frase: cada modelo continua fazendo a sua parte, mas todos passam a entregar o resultado num
**formato único (a evidência)**. Uma **camada de síntese** liga as evidências com **regras escritas e
públicas**, e cada porquê do relatório é uma **cadeia de evidências** que dá para conferir até o número de
origem.

## 2. O que já existe (não refazer)

| Peça | Onde | O que dá para o desenho |
|---|---|---|
| Demonstrações "como era na data" | `base/ponto_no_tempo.py` | cada valor com o dia em que ficou público |
| Padrões por setor e notas (ótimo a péssimo, barato a caro) | `src/padroes.py`, `src/notas.py` | evidências fundamentalistas com regra pública |
| DuPont, ciclo de caixa, cobertura de juros, caixa livre | `src/fundamentalista.py` | os números que os porquês explicam |
| Juros, inflação e Focus, com a data de divulgação | `src/juros_e_inflacao.py`, `src/bcb.py` | evidências macro sem olhar o futuro |
| Proveniência, versão da fórmula, "indisponível com motivo" | `src/analise.py` | o rodapé de cada evidência |
| ML que precisa vencer a previsão ingênua | `src/aprendizado.py`, `trader/` (pré-registro M2) | evidências quantitativas honestas |
| Relatório da empresa em seções, mesmo objeto para tela e PDF | `src/relatorio_empresa.py` | onde os porquês aparecem |

## 3. A evidência: o formato único

Todo modelo, de qualquer tipo, devolve uma lista de evidências. Tipos simples, prontos para virar JSON
(regra do `CLAUDE.md`: pronto para trocar de interface).

```python
@dataclass(frozen=True)
class Evidencia:
    id: str                 # "fund.cobertura_de_juros.ruim", estável entre versões
    tipo: str               # "macro" | "tecnico" | "fundamentalista" | "quantitativo"
    ativo: str | None       # "PETR4.SA"; None para evidência de mercado (a Selic)
    frase: str              # "A cobertura de juros caiu para 1,8 vez (era 3,1 um ano antes)."
    valor: float | None
    unidade: str            # "vezes", "%", "pontos"
    data_de_corte: date     # o relatório "como era" nesta data
    divulgado_em: date | None  # quando o número ficou público (nunca depois do corte)
    fonte: str              # "CVM, ITR 2T26, versão 1" | "BCB, SGS 432"
    regra: str              # "padroes/cobertura_de_juros@1": a regra e a versão dela
    forca: str              # "fato" | "padrao" | "modelo"
    acerto: Acerto | None   # só para forca="modelo" (seção 5)
    limites: tuple[str, ...]  # o que esta evidência NÃO diz
```

- **`forca` separa três coisas que o relatório nunca mistura:** um *fato* (a Selic é 10,5%), um
  *padrão* (a margem está no pior quinto do setor) e uma *saída de modelo* (a volatilidade prevista
  para o próximo mês).
- **Sem número, sem evidência.** "Indisponível com motivo" (como em `src/analise.py`) também é uma
  evidência, com `valor=None`, sem data de divulgação e o motivo na frase.

## 4. O que cada tipo de modelo entrega

| Tipo | Exemplos de evidência | De onde vem hoje |
|---|---|---|
| Macro | Selic subiu 1 ponto em 6 meses; o Focus espera IPCA acima da meta; juro real alto | `juros_e_inflacao.py`, trilha Macro (`tickerlab-fontes`, ADR 0064) |
| Fundamentalista | dívida líquida ÷ EBITDA alta para o setor; cobertura de juros caindo; ciclo de caixa maior | `fundamentalista.py`, `notas.py`, `padroes.py` |
| Técnico | preço abaixo da média de 200 dias; drawdown de 35%; volatilidade no maior décimo de 5 anos | `indicadores.py`, `metricas.py` |
| Quantitativo | volatilidade prevista (HAR) acima da média; correlação com o Ibovespa subiu; exposição a juros (beta à curva) | `aprendizado.py`, `correlacao.py`, `trader/` |

As evidências de **direção de preço** ("vai subir") ficam de fora do relatório: o próprio
`src/aprendizado.py` mostra que prever o sinal do dia seguinte dá quase o mesmo que o acaso. Os
porquês do relatório falam de **risco, fundamentos e sensibilidade**, onde os números têm chance de
dizer algo.

## 5. Quando um modelo pode falar

Uma evidência com `forca="modelo"` só entra no relatório se o modelo:

1. **venceu a previsão ingênua** (amanhã igual a hoje, média histórica) fora da amostra, com o critério
   escrito **antes** de ver o resultado, como nos pré-registros da M2;
2. leva no campo `acerto` o tamanho da vitória e o período: `Acerto(metrica="erro médio",
   modelo=0.21, ingenuo=0.27, periodo="2015-2025", testado_em=date(...))`;
3. tem a versão registrada: modelo novo, versão nova; o relatório antigo continua dizendo qual usou.

Modelo que não venceu o ingênuo **não some**: ele vai para a página de metodologia como resultado
negativo. A regra do `CLAUDE.md` é mostrar o que não funciona.

## 6. A síntese: os porquês

Um **porquê** é uma pergunta com uma resposta montada por uma **cadeia de evidências**, ligadas por
**elos escritos à mão**, um arquivo por elo, com versão, na pasta `regras/elos/`:

```yaml
# regras/elos/juros-e-divida-flutuante.yaml   (versão 1)
pergunta: "Por que o lucro de {empresa} pode sofrer com os juros?"
precisa:
  - macro.selic.subiu                       # a Selic subiu 1 ponto ou mais em 12 meses
  - fund.divida_liquida_ebitda.alta         # dívida no pior quinto do setor
  - fund.divida_atrelada_ao_cdi.maioria     # mais da metade da dívida em CDI (nota explicativa / FRE)
explica: >
  Dívida em CDI fica mais cara quando a Selic sobe. Com dívida alta, a despesa financeira pesa
  mais no lucro. Isso já aconteceu com a cobertura de juros, que caiu de {antes} para {agora}.
contra:                                     # o que enfraquece a cadeia (sempre mostrado)
  - fund.caixa_liquido.positivo
  - fund.hedge_de_juros.informado
```

O relatório mostra a pergunta, a resposta e, embaixo, **cada elo com o número, a fonte e a data**.

Regras da síntese:

- **Só liga evidências que existem.** Faltou um elo: o porquê não aparece (ou aparece como "não deu para
  responder: falta X").
- **O contra sempre aparece.** Se a empresa tem caixa líquido, a resposta diz isso ao lado.
- **Evidências que discordam ficam as duas na tela.** A síntese não escolhe um lado.
- **Nada de "compre" ou "venda".** A resposta explica um mecanismo; não diz o que fazer.
- **Sem IA paga por token** (decisão C-03): as frases são moldes com números, como na Newsletter.

### Como "os modelos aprendem" a fazer porquês

Sem IA paga por token, o aprendizado entra em dois lugares, os dois medidos:

1. **Quais elos valem:** para cada elo, um teste "sem olhar o futuro" na base: nas empresas e datas em
   que a cadeia apareceu, o efeito explicado (a despesa financeira subir, a margem cair) aconteceu
   mais vezes do que nas outras? O elo só entra no relatório se passar, e a taxa de acerto aparece ao
   lado ("em 2010-2025, 71% das vezes; nas outras empresas, 38%").
2. **Quanto cada evidência pesa:** num modelo de previsão de risco (volatilidade, queda de margem), a
   contribuição de cada variável vira a resposta de "o que mais pesou?". Isso só vale para um modelo
   que passou na seção 5.

Elo que deixa de funcionar com dados novos perde o selo e sai do relatório na próxima versão.

## 7. Como aparece no relatório (tela e PDF)

Uma seção nova, **"Por quê?"**, no relatório completo de empresa (`src/relatorio_empresa.py`), logo
depois do resumo:

- até 5 porquês, primeiro os que têm o maior acerto medido;
- cada um abre em: resposta curta → elos (número, fonte, data) → o que pesa contra → limites;
- o PDF lê o mesmo objeto; a seção "Limites e cuidados" continua obrigatória e ganha a linha
  "os porquês explicam mecanismos observados no passado; não são previsão nem recomendação".

## 8. Rota da API (para a interface nova)

```
GET /v1/empresas/{codigo}/evidencias?data=2026-10-14
GET /v1/empresas/{codigo}/porques?data=2026-10-14
```

Os dois devolvem o mesmo JSON que o relatório usa. Mesma data, mesmo resultado (o
`id_da_execucao` de `src/analise.py`).

## 9. Etapas (um PR cada, com testes)

1. **O tipo `Evidencia`** em `src/evidencias.py` e um adaptador que transforma as notas e os padrões que já
   existem em evidências. Teste: o mesmo número da tela; cortar o futuro não muda o passado.
2. **Evidências macro** a partir de `juros_e_inflacao.py`, com a data de divulgação. Teste: uma evidência
   não aparece antes de o número ser público.
3. **Elos e síntese:** o leitor de `regras/elos/`, a montagem das cadeias e os 3 primeiros elos
   (juros e dívida; câmbio e exportadora; inflação e margem do varejo). Teste: faltou um elo, nada de
   porquê; o contra sempre aparece.
4. **O teste de cada elo na base** (a taxa de acerto da seção 6), com o critério escrito antes, num
   pré-registro como os da M2.
5. **A seção "Por quê?"** no relatório e no PDF.
6. **Evidências quantitativas** (volatilidade prevista) com o `Acerto` contra o ingênuo.
7. **As rotas da API** (com a v1 ligada).

## 10. Decisões

- **Quantos porquês por relatório:** até 5 (Tiago, 14/10/2026).
- **Plano:** só no **Pro** (Tiago, 14/10/2026). O limite entra em `src/planos.py` na etapa 5, quando a
  seção aparecer.
- **Em aberto: critério mínimo de um elo:** proposta: acerto pelo menos 15 pontos acima das outras empresas, com
  pelo menos 30 casos; o número exato vai no pré-registro da etapa 4.
- **Em aberto: regulatório.** Porquês por empresa chegam mais perto de "análise" do que as notas. Vale incluir no
  pedido de parecer jurídico que já está pendente para a Newsletter (decisão 0020).
