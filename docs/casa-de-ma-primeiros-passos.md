# TickerLab Data para a equipe: instalação e primeiros 10 minutos

Guia para quem **não programa**. Você vai instalar um programa pequeno (`tickerlab`) no seu PC com Windows, colar a sua
chave e consultar empresas pelo CNPJ. Cada número vem com a fonte e a data. Nada aqui é recomendação de investimento.

**O que você precisa receber:** uma chave pessoal, que começa com `tld_`. Ela é só sua: quem a tem consulta em seu nome
e gasta a cota da organização. Não mande por e-mail nem em grupo de mensagens. Se perder ou desconfiar que vazou, avise
quem te entregou: a chave é cancelada na hora e você ganha outra.

> Estado em 10/11/2026: a API ainda não está ligada para o público. Os passos 2 e 3 do roteiro dependem de comandos
> ainda em construção (marcados com 🚧). O guia será atualizado quando entrarem.

## 1. Instalar (uma vez, uns 10 minutos)

Abra o **Windows PowerShell** (menu Iniciar, digite `PowerShell`). Copie cada bloco, cole e aperte Enter.

**a) Python e Git** (pule o que já tiver; confira com `python --version` e `git --version`):

```powershell
winget install Python.Python.3.12
winget install Git.Git
```

Feche e abra o PowerShell de novo depois de instalar.

**b) O programa `tickerlab`** (instala em separado dos seus outros programas, com o `pipx`):

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

> Se a sua empresa bloqueia instalar programas, peça à TI para liberar Python 3.11 ou mais novo e Git, ou avise quem te
> deu a chave: existe um caminho com arquivo pronto (a combinar).

## 2. Colar a chave (uma vez)

```powershell
tickerlab login
```

Cole a chave quando pedir (ela **não aparece** enquanto você cola, é normal) e aperte Enter. A chave fica guardada só no
seu usuário do Windows. Para conferir: `tickerlab consumo` mostra quantos pedidos a sua organização já usou no mês.

## 3. Roteiro de 10 minutos

Troque os CNPJs pelos que você quer. O CNPJ pode ter pontos e barra.

**Minuto 1: ver o que a sua chave pode pedir** (não gasta cota)

```powershell
tickerlab catalogo
```

**Minutos 2 a 4: prospectar um setor** (🚧 `setor` está em revisão, PR 965)

```powershell
tickerlab setor
```

Sem nada depois, lista os setores disponíveis (não gasta cota). Com o nome de um setor, mostra o que a base sabe dele,
com fonte e data em cada linha. 🚧 A lista de empresas de um setor com porte e região (`tickerlab prospectar`) ainda não
existe: entra com a linha 794 e a 773 da fila do projeto.

**Minutos 5 a 7: abrir a ficha de uma empresa**

```powershell
tickerlab empresa 00.000.000/0001-91
```

Mostra situação cadastral, razão social, natureza jurídica e se é do Simples, direto da Receita Federal. Para ver como
a empresa **era** numa data: `tickerlab empresa 00.000.000/0001-91 --como-era 2024-12-31`.
Se for companhia aberta, as demonstrações (DFP e ITR da CVM): `tickerlab demonstracoes <CNPJ>`.
🚧 A ficha completa (vínculos, eventos e comparáveis em um só comando) depende da linha 736 e da 773.

**Minutos 8 a 9: comparar duas empresas**

Rode `tickerlab empresa` (ou `demonstracoes`) para cada CNPJ e compare os números lado a lado. 🚧 O comando que compara
sozinho (`comparaveis`) ainda não existe.

**Minuto 10: levar para a planilha**

Adicione `--json` ao final de qualquer comando para receber os dados em formato de máquina, e salve num arquivo:

```powershell
tickerlab demonstracoes 00.000.000/0001-91 --json > demonstracoes.json
```

No Excel: aba **Dados**, **Obter Dados**, **De Arquivo**, **De JSON**. 🚧 A exportação direta para planilha (`exportar`)
é a linha 782 e ainda não existe.

## 4. Quando algo dá errado

| Você vê | O que quer dizer | O que fazer |
|---|---|---|
| `Nenhuma chave da API configurada` | Você ainda não colou a chave neste PC | `tickerlab login` |
| `A API recusou a chave (inválida, revogada ou vencida)` | Chave errada, cancelada ou vencida | Rode `tickerlab login` de novo com cuidado (a chave inteira, sem espaço). Persistindo, peça outra |
| `Limite de pedidos por minuto atingido: tente de novo em N segundos` | Muita gente consultando ao mesmo tempo | Espere o tempo dito e repita |
| `A quota de pedidos do mês acabou` | A organização gastou os pedidos do mês | `tickerlab consumo`; volta no dia 1º. Avise quem coordena o acesso |
| `Não há dado disponível para este pedido` | O CNPJ não tem aquele dado, ou não está no contrato | Confira o CNPJ; veja `tickerlab catalogo` |
| `CNPJ inválido` | Dígito errado ou faltando | Confira os 14 caracteres |
| `A API está fora do ar agora` | Problema do nosso lado | Tente em alguns minutos |

Pessoas físicas (sócios, MEI, empresários individuais, contatos) **não** saem pela API, de propósito.

## 5. Para quem coordena (não é para os analistas)

- Cada pessoa tem uma chave. Todas dividem a mesma cota da organização; cancelar uma chave não afeta as outras.
- Quem emite, cancela e acompanha chaves é o administrador do TickerLab: `scripts/chaves_da_api.py` (comandos
  `emitir-chaves`, `revogar-chave`, `ver`). A saída com as chaves é entregue **uma vez** e cada chave vai só à pessoa dela.
- O consumo da organização aparece em `tickerlab consumo`.

## 6. Passo a passo do administrador (só o Tiago roda; nada disso foi executado)

Pré-requisitos: o "pode" do beta (linha 569), a cota decidida e a lista de quem recebe chave. O plano `piloto` hoje
comporta só **3 chaves ativas** (`src/planos.py`): para 50 pessoas é preciso um plano com mais chaves, decisão de cota.

1. Criar a organização: `criar-organizacao --nome "<casa>" --cnpj <cnpj>`; anotar o id.
2. Conceder os direitos do contrato: `conceder-direito <id> --conjunto <c> --finalidade analise --desde AAAA-MM-DD`.
3. Emitir uma chave por pessoa, guardando a saída **só num arquivo seu** (a saída traz as chaves):
   `emitir-chaves <id> --rotulos "Ana,Bruno,..." > chaves-entrega.csv`. O banco guarda só o prefixo, nunca o nome.
4. Entregar cada chave só à pessoa dela, por canal privado. Depois, apagar o arquivo.
5. Acompanhar: `ver <id>` (chaves, direitos, consumo). Saída de pessoa: `revogar-chave <id> <chave>`.

No VPS o script roda assim (em `/opt/stacks/tickerlab`):
`docker exec -i tickerlab python - emitir-chaves <id> --quantidade 50 < scripts/chaves_da_api.py`.
