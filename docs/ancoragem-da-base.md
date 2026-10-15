# Âncora da base no Bitcoin (OpenTimestamps)

ADR 0078 (aceita em 15/10/2026). Código: `base/ancoragem.py` (raiz de Merkle) e `scripts/ancorar_base.py` (recibo `.ots`).

## Para que serve

Provar a qualquer pessoa, sem precisar confiar no TickerLab, duas coisas:

1. **Integridade:** a versão da base que o cliente tem é exatamente a que foi publicada.
2. **Data:** essa versão (ou um pré-registro de pesquisa, ou um lote de rótulos) já existia num dia,
   porque um resumo dela entrou num bloco do Bitcoin, que ninguém consegue reescrever.

## Três ideias, em português

- **Hash (SHA-256):** uma "impressão digital" de 32 bytes de qualquer arquivo. O mesmo arquivo dá
  sempre o mesmo hash; mudar uma vírgula muda o hash inteiro; e não dá para voltar do hash ao
  arquivo. Cada tabela da base já tem o hash do conteúdo no manifesto (`base/parquet.py`).
- **Raiz de Merkle:** juntar muitos hashes num só. Os hashes das tabelas são as **folhas**; cada par
  vira um hash novo, e assim por diante até sobrar um: a **raiz**. Se qualquer tabela mudar, a raiz
  muda. E dá para provar que uma tabela está na raiz mostrando só os "irmãos" do caminho (a **prova
  de inclusão**), sem mostrar as outras tabelas. Seguimos a RFC 6962 (a mesma dos certificados da
  web): prefixo 0x00 nas folhas e 0x01 nos nós, para uma folha nunca se passar por um nó.
- **Recibo `.ots`:** o OpenTimestamps junta os hashes de muita gente e grava um único resumo numa
  transação do Bitcoin. O recibo é o caminho de contas que leva do hash da nossa âncora até esse
  bloco. Primeiro ele fica **pendente** (uma promessa dos calendários); horas depois, o `atualizar`
  troca a promessa pelo caminho até o bloco. Grátis para nós (quem paga a transação são os
  calendários).

## O que sai da máquina

| Passo | O que vai pela internet | Para onde |
|---|---|---|
| `montar` | nada | — |
| `carimbar` | 32 bytes: SHA-256 de (hash da âncora + 16 bytes aleatórios) | 4 calendários públicos do OpenTimestamps |
| `atualizar` | os mesmos 32 bytes | os calendários que receberam (só os da lista oficial) |
| `conferir` | a altura do bloco | mempool.space e blockstream.info (precisam concordar) |

Nenhum dado da base, nenhuma linha e nenhum hash de registro individual sai. A âncora leva só os
nomes das tabelas e os hashes dos manifestos; tabela de pessoas com menos de 50 linhas nem entra.

## Exemplo de ponta a ponta (15/10/2026, base de mentira)

```powershell
# 1. Montar a âncora de uma versão da base (aqui, duas tabelas de mentira)
python -m scripts.ancorar_base montar ancoras/base-demo-2026-10-15.json --rotulo demo-2026-10-15 --pasta demo/base
#    raiz: a59b0f52f78018a7959f09a0edd7a3aaf706c6b6360daa8f9631c180547f24c7

# 2. Carimbar: grava ancoras/base-demo-2026-10-15.json.ots (os 4 calendários aceitaram)
python -m scripts.ancorar_base carimbar ancoras/base-demo-2026-10-15.json

# 3. Conferir logo depois
python -m scripts.ancorar_base conferir ancoras/base-demo-2026-10-15.json --pasta demo/base
#    base igual à âncora
#    recibo é desta âncora
#    ainda pendente: rode `atualizar` daqui a algumas horas

# 4. Horas depois: pegar o bloco e conferir de novo
python -m scripts.ancorar_base atualizar ancoras/base-demo-2026-10-15.json.ots
python -m scripts.ancorar_base conferir ancoras/base-demo-2026-10-15.json --pasta demo/base
#    no Bitcoin desde o bloco <altura>: <data> (Brasília)
```

O passo 4 foi testado com um recibo já completo, o `examples/hello-world.txt.ots` do próprio
OpenTimestamps: o recibo é do arquivo e a raiz confere no **bloco 358391** (28/05/2015) nos dois
exploradores.

**Cliente que comprou só uma tabela** recebe a âncora pública, o recibo e uma prova de inclusão:

```powershell
python -m scripts.ancorar_base provar ancoras/base-demo-2026-10-15.json fca/emissores --saida prova.json
python -m scripts.ancorar_base conferir-prova prova.json demo/base/fca/emissores.json
#    fca/emissores: está na raiz a59b0f52f78018a7… (demo-2026-10-15)
```

E confere o próprio Parquet contra o manifesto com `base.parquet.conferir_tabela`. A corrente
completa: Parquet → hash da tabela no manifesto → folha → raiz → âncora → recibo → bloco do Bitcoin.

## Rotina no servidor de casa

Toda noite às 0h15 o cron roda `noite` (wrapper `~/bin/ancorar-base.sh`, marca `ancoras` no
`rodar-tarefa.sh`, aviso no Kuma pelo `conferir-tarefas-casa.sh`):

```bash
python -m scripts.ancorar_base noite --ancoras /ancoras --pasta <acervo>/base --rotulos <acervo>/rotulos_ia/v1
```

1. **Base:** se a base mudou desde a última âncora, monta `base-AAAA-MM-DD.json` (dia de Brasília).
   Se o arquivo do dia já existe, não faz outro: no máximo uma âncora por dia.
2. **Rótulos:** cada lote com `estado: gravado` no `manifesto.json` ganha `rotulos-<lote>.json`
   (o `rotulos.jsonl` e o `manifesto.json` daquele momento).
3. **Carimbar** toda âncora que ainda não tem `.ots` (inclusive a de uma noite em que os
   calendários estavam fora do ar).
4. **Atualizar** os recibos sem bloco. Recibo pendente há mais de 2 dias vira uma linha `FALHAS:`
   e saída 1, e o Kuma fica "down".

A pasta `ancoras/` nunca é sobrescrita. O acervo entra no contêiner só para leitura.

## Pré-registro e auditoria, à mão

Pré-registros (ADR 0006) e auditorias do Tiago (ADR 0072) são raros: monte e carimbe na hora, antes
da primeira execução ou logo depois da auditoria, e o `noite` cuida do `atualizar`:

```bash
python -m scripts.ancorar_base montar /ancoras/prereg-m2-v0.4.json --rotulo m2-v0.4 --arquivo docs/pre-registro-m2-v0.4.md
python -m scripts.ancorar_base carimbar /ancoras/prereg-m2-v0.4.json
```

## Limites

- **Data mínima, não máxima:** o recibo prova que a âncora existia *até* a hora do bloco, não que
  foi feita naquele dia. Ancorar cedo e sempre é o que dá valor.
- **Não prova que o dado está certo:** prova que não mudou depois. A qualidade continua sendo o
  critério de pronto da ADR 0027.
- **Exploradores:** o `conferir` confia em dois exploradores públicos que precisam concordar. Quem
  tiver um nó do Bitcoin pode conferir sem confiar em ninguém (`ots verify`, ou o nó de casa num PR
  seguinte).
- **Windows:** o programa `ots` oficial não abre (a `python-bitcoinlib` procura o OpenSSL por
  `ctypes`); por isso o script usa a biblioteca `opentimestamps` direto. Acentos trocados no
  terminal: `$env:PYTHONIOENCODING = "utf-8"`.
- **Licença:** `opentimestamps` e `python-bitcoinlib` são LGPL-3.0 (usadas como biblioteca, sem
  mudança, o que a LGPL permite em código fechado); `pycryptodomex` é BSD. Só no `requirements.txt`,
  fora da imagem do app.
