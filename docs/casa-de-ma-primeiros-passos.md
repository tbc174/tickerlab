# TickerLab Data: instalação e roteiro de 10 minutos (apresentação de 20/11/2026)

Guia para quem **não programa**. Você vai instalar um programa pequeno (`tickerlab`) num PC com Windows, colar uma chave
e consultar empresas pelo CNPJ. Cada número vem com a fonte e a data. Nada aqui é recomendação de investimento.

**O que você precisa receber:** uma chave pessoal, que começa com `tld_`. Ela é só sua: quem a tem consulta em seu nome
e gasta a cota da organização. Não mande por e-mail nem em grupo de mensagens. Se perder ou desconfiar que vazou, avise
quem te entregou: a chave é cancelada na hora e você ganha outra.

> **Estado em 10/11/2026:** a API ainda não está ligada em produção (espera o "pode" do beta, linha 569). Os pontos
> marcados com 🚧 dependem de comandos ou dados que ainda estão em construção; o guia é atualizado quando entrarem.

## 1. Instalar (uma vez, uns 10 minutos)

Abra o **Windows PowerShell** (menu Iniciar, digite `PowerShell`). Copie cada bloco, cole e aperte Enter.

**a) Python e Git** (pule o que já tiver; confira com `python --version` e `git --version`):

```powershell
winget install Python.Python.3.12
winget install Git.Git
```

Feche e abra o PowerShell de novo depois de instalar.

**b) O programa `tickerlab`** (instala separado dos seus outros programas, com o `pipx`):

```powershell
python -m pip install --user pipx
python -m pipx ensurepath
```

Feche e abra o PowerShell mais uma vez e rode:

```powershell
pipx install "git+https://github.com/tbc174/tickerlab#subdirectory=cli"
tickerlab --help
```

Se aparecer a lista de comandos, está instalado. Para atualizar no futuro: `pipx upgrade tickerlab`.

> Se o PC da empresa bloqueia instalar programas, peça à TI para liberar Python 3.11 ou mais novo e o Git.

**c) Acentos no PowerShell antigo.** No "Windows PowerShell" (o azul, versão 5.1) letras como `ç` e `ã` podem sair
trocadas por símbolos. Antes de usar, rode uma vez por janela:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

(O Windows Terminal e o PowerShell 7 já saem certos.)

## 2. Colar a chave (uma vez)

```powershell
tickerlab login
```

Cole a chave quando pedir (ela **não aparece** enquanto você cola, é normal) e aperte Enter. A chave fica guardada só no
seu usuário do Windows. Para conferir: `tickerlab consumo` mostra quantos pedidos a organização já usou no mês.

## 3. Roteiro de 10 minutos

O exemplo é o **setor elétrico**: um setor com fonte oficial própria (ANEEL) e companhias abertas (CVM) que se cruzam com
o cadastro da Receita. As três empresas abaixo são companhias abertas do setor. Troque pelos CNPJs que quiser; pontos e
barra são aceitos.

| Empresa | CNPJ |
|---|---|
| CPFL Energia | 02.429.144/0001-93 |
| Cemig | 17.155.730/0001-64 |
| Copel | 76.483.817/0001-20 |

**Minuto 1: ver o que a sua chave pode pedir** (não gasta cota)

```powershell
tickerlab catalogo
```

**Minutos 2 a 4: prospectar um setor**

```powershell
tickerlab setor
tickerlab setor eletricas
```

O primeiro lista os setores disponíveis (não gasta cota). O segundo mostra o tamanho do mercado, a concentração
(CR4 e HHI) por ano e quem são as companhias abertas do setor, com fonte e data em cada número.
🚧 A lista de empresas de um setor com porte e região, inclusive as fechadas (`tickerlab prospectar`), ainda não existe:
entra com as linhas 794 e 773 da fila.

**Minutos 5 a 7: abrir a ficha de uma empresa**

```powershell
tickerlab empresa 02.429.144/0001-93
tickerlab demonstracoes 02.429.144/0001-93
```

O primeiro traz o perfil: situação cadastral, razão social, natureza jurídica e Simples, direto da Receita Federal, e,
de companhia aberta, cada DFP e ITR devida, com o prazo da CVM, quando saiu, os dias úteis de atraso e a situação
(`on_time` no prazo, `gray_zone` atraso curto, `late`, `severely_late`, `not_filed`). O segundo traz DFP e ITR da CVM,
cada conta com o documento, a versão e a data de entrega. Para ver como a empresa **era** numa data: acrescente
`--como-era 2024-12-31`.
🚧 Os vínculos e os comparáveis na mesma ficha dependem das outras rotas da linha 736.

**Minutos 8 a 9: comparar**

Rode os mesmos dois comandos para a Cemig (17.155.730/0001-64) e a Copel (76.483.817/0001-20) e compare os números lado a
lado. 🚧 O comando que compara sozinho (`comparaveis`) ainda não existe.

**Minuto 10: levar para a planilha**

Acrescente `--planilha` e o nome do arquivo a qualquer comando de empresa, fundo ou setor:

```powershell
tickerlab demonstracoes 02.429.144/0001-93 --planilha cpfl.xlsx
```

O `.xlsx` abre direto no Excel: uma aba por tabela, cada linha com a fonte e a data em que o dado ficou público, e a aba
`fontes` com a frase de atribuição que a licença pede. Prefere CSV? Use `--planilha cpfl.csv` (separado por ponto e
vírgula, com vírgula decimal, um arquivo por tabela).
🚧 A apresentação pronta (`exportar`, o deck) é a linha 782 e ainda não existe.

### Quanto o roteiro gasta de cota

Cada consulta a uma empresa ou setor gasta **1 pedido**; `catalogo`, `consumo` e a lista de `setor` não gastam. O roteiro
acima (setor + 3 empresas + 3 demonstrações) gasta **7 pedidos**. O plano `piloto` tem 10.000 por mês e 60 por minuto: dá
para ~1.400 execuções completas, e o limite por minuto não é atingido por uma pessoa só.

## 4. Quando algo dá errado

| Você vê | O que quer dizer | O que fazer |
|---|---|---|
| `Nenhuma chave da API configurada` | Você ainda não colou a chave neste PC | `tickerlab login` |
| `A API recusou a chave (inválida, revogada ou vencida)` | Chave errada, cancelada ou vencida | `tickerlab login` de novo, com a chave inteira e sem espaço. Persistindo, peça outra |
| `Limite de pedidos por minuto atingido: tente de novo em N segundos` | Muita gente consultando ao mesmo tempo | Espere o tempo dito e repita |
| `A quota de pedidos do mês acabou` | A organização gastou os pedidos do mês | `tickerlab consumo`; volta no dia 1º. Avise quem coordena |
| `Não há dado disponível para este pedido` | O CNPJ não tem aquele dado, ou não está no contrato | Confira o CNPJ; veja `tickerlab catalogo` |
| `CNPJ inválido` | Dígito errado ou faltando | Confira os 14 caracteres |
| `A API está fora do ar agora` | Problema do nosso lado | Tente em alguns minutos |

Pessoas físicas (sócios, MEI, empresários individuais, contatos) **não** saem pela API, de propósito.

## 5. Ensaio no PC do Tiago, contra a API local (rede de segurança)

Se a produção não estiver liberada no dia, o mesmo roteiro roda contra a API ligada no próprio PC, com a base local. O
`tickerlab` só troca o endereço (`TICKERLAB_API_URL`). Tudo vive numa pasta **fora do repositório, do OneDrive e do
`TickerLab-Acervo`** (no ensaio de 10/11: `C:\Users\tiago\TickerLab-Ensaio`, com `acervo\base`, `dossies\atual`,
`ensaio.db` e a chave).

1. **Base:** o mesmo recorte que vai ao VPS (`python -m scripts.montar_recorte_da_api --degrau 2`), gerado na VM de casa
   (a base inteira lá, sem pessoa) e copiado para `<pasta>\acervo\base`. Fichas: a última noite de
   `acervo\dossies\<dia>` copiada para `<pasta>\dossies\atual`. **Antes de usar, conferir por contagem que não há
   pessoa** (nenhuma chave de sócio/administrador, nenhum padrão de CPF); achou, para e avisa a Diretoria.
2. **Banco e chave:** `$env:TICKERLAB_DATABASE_URL = "sqlite:///<pasta>/ensaio.db"` e
   `python -m scripts.ensaio_local --saida-da-chave <pasta>\chave.txt` (migrações, administrador de ensaio,
   organização, direitos dos cinco conjuntos e a chave, que só vai para o arquivo).
3. **Subir a API** com `TICKERLAB_AMBIENTE=ensaio`, `TICKERLAB_API_EXTERNA=1`, `TICKERLAB_ACERVO=<pasta>\acervo`,
   `TICKERLAB_DOSSIES=<pasta>\dossies` e `uvicorn src.api:app --port 8765`. Com `TICKERLAB_AMBIENTE=ensaio` (valor exato),
   `base.prontidao.registro_vigente()` dá a toda tabela do dicionário uma prova de ensaio (do dia anterior), sem tirar
   o registro de verdade; com qualquer outro valor, inclusive `producao` ou nenhum, nada muda e o portão responde
   `sem_prontidao` como em produção (há teste dos dois lados).
4. `$env:TICKERLAB_API_URL = "http://127.0.0.1:8765"`, `tickerlab login` e o roteiro da seção 3.

**O que responde, rota por rota (ensaio de 10/11/2026, recorte do degrau 2 e fichas de 07/11; cada "sim" vale "com
prontidão de ensaio", não com a prontidão real da linha 784):**

| Rota | Resposta | O que a faz responder / falta |
|---|---|---|
| `/data/v1/catalog`, `/usage` | sim (200) | só o banco local |
| `/data/v1/companies/{cnpj}/financials` | sim (200) | `demonstracoes_como_era` do recorte |
| `/data/v1/sectors` e `/sectors/{setor}` | sim (200; `eletricas` com ~99 KB) | fichas de `dossies/atual` |
| `/data/v1/funds/{cnpj}` | sim (200), **só a carteira** | CDA do recorte; o **cadastro** (taxas, classe) não sai porque o registro de coletas, que dá a data de publicação, não está no recorte |
| `/data/v1/companies` (prospecção) | sim (200) | as duas tabelas de empresas só-PJ do recorte (linha 796) |
| `/data/v1/companies/{cnpj}/events`, `/links`, `/comparables` | sim (200) | `eventos`, `trocas_de_auditor`, `fca_geral` do recorte e a **rede** (entidades, identificadores, ligações) copiada sem pessoa nem MEI (contagem: 0 de pessoa, 0 de MEI) |
| `/data/v1/buyers` (quem compraria) | sim (200), **só o sinal de sócia PJ** (`took_stake`) | `entradas_de_socio_pj` (901.446 linhas, copiada da VM só para leitura, guarda PJ com PJ conferida: 0 linha fora da lista sem pessoa) com as duas tabelas de empresas do recorte. **Controladas (`controls_in_sector`) e fundos (`fund_stake`) ficam em casa**: fora de casa só sai o sinal de sócia PJ, e a apresentação não deve prometer os outros dois. Setor por CNAE de 5 ou 7 dígitos (`cnae=62015`, `years` até 10, `state` opcional) |
| `/data/v1/companies/{cnpj}` e `/profile` (a ficha) | sim (200), **só no ensaio** | `cnpj_situacao_cadastral` **derivada do retrato vigente** (2026-10, público desde 21/10): só PJ do recorte, só códigos. Consulta com `known_at` antes de 21/10 dá `not_available` |
| `/data/v1/buyers` (compradores do setor; no conector, `compradores_do_setor`, #1036) | **não** | A chave do ensaio não tem o conjunto `buyers` (`CONJUNTOS_DO_ENSAIO` em `scripts/ensaio_local.py`), então a ferramenta nem aparece no conector, e o recorte de 10/11 não tem `entradas_de_socio_pj`. Para responder, é preciso refazer o recorte do degrau 2, que agora leva `entradas_de_socio_pj`, e dar `buyers` à organização do ensaio. Mesmo assim, só sai o sinal `took_stake` (entrou como sócia PJ). `controladas` fica em casa e `registro_de_fundos` não vai em nenhum degrau, então `controls_in_sector` e `fund_stake` não aparecem nem no ensaio nem na produção. Conferido pela leitura do código em 11/11, sem rodar |

**O que a ficha mostra no ensaio e NÃO mostrará em produção enquanto a linha 841 (montagem real da situação
cadastral mês a mês, mesa Dados) não fechar:** a situação cadastral, a data e o motivo, o mês do retrato e a matriz.
No ensaio ela é um único retrato (2026-10); em produção só haverá a série de verdade depois da 841. **Não prometer na
apresentação a ficha cadastral "como era" em datas antigas nem a série de situações.** A situação, a razão social e o
Simples do histórico datado (linha 686) também dependem de tabelas que só o ensaio tem hoje. O que está na produção
na segunda é só o que a seção 5 marca como carregado lá.

Limites do ensaio: roda sem a internet e sem o VPS, mas **depende da VM de casa para refazer a base** (o recorte sai de
lá). Serve de base para um conector local (linha 570).

## 6. Para quem coordena

- Hoje o plano `piloto` permite **3 chaves ativas** por organização, que dividem a mesma cota; cancelar uma chave não
  afeta as outras. Chave por pessoa para 50 pessoas só depois da apresentação (linha no fim da fila).
- Criar a organização, emitir e entregar a chave é só do Tiago: `scripts/chaves_da_api.py`
  (`criar-organizacao`, `conceder-direito`, `emitir-chave`, `revogar-chave`, `ver`). A chave sai **uma vez** na tela; entregue
  só à pessoa e não guarde cópia.
- O consumo da organização aparece em `tickerlab consumo`.
