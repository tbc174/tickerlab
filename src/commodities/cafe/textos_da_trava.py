"""Os textos do simulador de trava do café: avisos, rótulos e os riscos de cada instrumento (linha 340).

Num lugar só para a tela e para a futura rota da API. Regra fixa (Tiago, 23/10/2026; CVM 19; ADR 0047):
nenhuma frase diz o que fazer, nem aponta o instrumento que teria dado mais margem; há teste que varre
estes textos atrás de verbo de conselho. Texto público: muda só com o "pode" do Tiago.
"""

from dataclasses import dataclass

from src.commodities.cafe import trava
from src.commodities.painel_de_precos import ATRIBUICAO, AVISO_DIARIO
from src.dividendos_e_custo import formatar_reais

__all__ = ["ATRIBUICAO", "AVISO_DIARIO"]  # a tela mostra os mesmos do painel de preços

INTRODUCAO = (
    "Você informa a sua produção e a conta mostra o que teria acontecido, em cada safra desde 2000, com "
    "cada forma de travar o preço, lado a lado com os riscos de cada uma. Quem escolhe a parte travada é "
    "você; a conta só refaz o passado com o preço de referência mensal."
)
AVISO_SEM_RECOMENDACAO = (
    "Isto é uma simulação com números do passado e os dados que você informou: não é recomendação de "
    "investimento, não diz o que fazer agora e não prevê o preço da próxima safra."
)
AVISO_SO_NA_MEMORIA = "Nada do que você digitar é guardado: a conta é feita na hora e some quando você fecha a página."
SEM_PRECOS = (
    "O preço de referência do café ou a PTAX ainda não foram coletados neste servidor "
    "(`python -m scripts.atualizar_series_macro`)."
)
SEM_SAFRAS = "Ainda não há safra com preço no mês da trava e no mês da colheita para esta combinação de meses."
FONTE_DO_CAMBIO = "Câmbio: Banco Central do Brasil, PTAX de venda, média do mês."

# Rótulos da entrada
ROTULO_TIPO = "Café"
NOMES_DOS_TIPOS = {"arabica": "Arábica", "robusta": "Robusta (conilon)"}
ROTULO_SACAS = "Sacas de 60 kg esperadas"
ROTULO_CUSTO = "Custo por saca hoje (R$)"
ROTULO_MES_DA_COLHEITA = "Mês da colheita (venda)"
ROTULO_ANTECEDENCIA = "Meses de antecedência da trava"
ROTULO_FRACAO = "Parte da safra travada (%)"
ROTULO_PREMIO = "Prêmio da opção de venda (% do preço na trava)"
AJUDA_PREMIO = (
    "O prêmio de verdade sai da bolsa no dia da compra e muda com o prazo e o nervosismo do mercado; aqui "
    "entra o número que você informar."
)
NOMES_DOS_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip

# Cabeçalhos dos resultados
TITULO_DO_RESUMO = "Margem por saca nos cenários de cada safra"
EXPLICACAO_DO_CENARIO = (
    "Cada safra vira um cenário: o preço andar, da trava até a colheita, como andou naquela safra, a partir "
    "do preço de hoje ({preco} por saca, média de {mes}). A margem é a receita desse cenário menos o custo "
    "que você informou. Assim o custo de hoje não é comparado com o real de anos atrás. Os instrumentos "
    "aparecem sempre na mesma ordem, sem classificação."
)
TITULO_DAS_SAFRAS = "Safra a safra, em reais da época"
EXPLICACAO_DAS_SAFRAS = (
    "Receita por saca de cada forma de travar, com a parte não travada vendida no mês da colheita. A coluna "
    "da chamada de margem é a maior quantia por saca que o futuro teria pedido de depósito entre a trava e "
    "a colheita."
)
TITULO_DOS_RISCOS = "Os riscos de cada forma de travar"
TITULO_DO_QUE_MUDARIA = "O que mudaria esta leitura"
O_QUE_MUDARIA = (
    (
        "Quebra de safra (geada, seca): com menos café colhido, a parte travada vira uma fração maior "
        "da produção; no termo pode faltar café para entregar, e no futuro o ganho dos contratos não "
        "cobre o café que não foi colhido."
    ),
    (
        "Câmbio: o café é cotado em dólar. O termo fixa reais; o futuro e a opção fixam dólares, e o "
        "câmbio da colheita continua aberto."
    ),
    (
        "Base local: o preço da sua região e da sua qualidade não é o da bolsa, e a diferença muda ao "
        "longo do ano. Esta conta não tem a base, porque o preço físico regional depende de licença."
    ),
    (
        "Preço diário: a trava, a chamada de margem e a colheita usam a média do mês. Num dia ruim, a "
        "chamada de verdade é maior que a mostrada aqui."
    ),
    "Custos da operação: corretagem, emolumentos, juros sobre a margem depositada e impostos não entram.",
)

COLUNA_SAFRA = "Safra"
COLUNA_TRAVA = "Mês da trava"
COLUNA_COLHEITA = "Mês da colheita"
COLUNA_PRECO_DA_TRAVA = "Preço na trava (R$/saca)"
COLUNA_PRECO_NA_COLHEITA = "Preço na colheita (R$/saca)"
COLUNA_CHAMADA = "Chamada de margem do futuro (R$/saca)"
COLUNA_INSTRUMENTO = "Forma de travar"
COLUNA_MENOR = "Menor margem (R$/saca)"
COLUNA_MEDIANA = "Mediana (R$/saca)"
COLUNA_MAIOR = "Maior margem (R$/saca)"
COLUNA_ABAIXO = "Safras abaixo do custo"


@dataclass(frozen=True)
class TextoDoInstrumento:
    chave: str
    nome: str
    como_funciona: str
    lado_bom: str
    lado_ruim: str
    o_que_nao_se_sabe: str


INSTRUMENTOS = (
    TextoDoInstrumento(
        "nao_travar",
        "Não travar",
        "Vende tudo no mês da colheita, ao preço daquele mês.",
        "Fica com toda a alta, se o preço subir até a colheita.",
        "Fica com toda a queda, se o preço cair até a colheita.",
        "O preço da colheita só se conhece na colheita.",
    ),
    TextoDoInstrumento(
        "termo",
        "Venda a termo (cooperativa ou trading)",
        "Fixa hoje, em reais, o preço da parte travada, para entregar o café na colheita.",
        "O preço em reais da parte travada não muda até a entrega, nem com o dólar.",
        "Risco de contraparte: se o preço subir muito, o comprador pode atrasar ou renegociar; se cair "
        "muito, o produtor que não tem o café para entregar fica devendo. Não há ganho com a alta na parte "
        "travada.",
        "A saúde financeira do comprador na hora da entrega.",
    ),
    TextoDoInstrumento(
        "futuro",
        "Futuro em bolsa (B3 ou ICE)",
        "Vende contratos em dólar na bolsa; na colheita vende o café no físico e zera os contratos. Aqui o "
        "preço de referência mensal faz o papel do futuro.",
        "Sem risco de contraparte: a bolsa garante o contrato.",
        "Chamada de margem: se o preço subir antes da colheita, a bolsa pede depósito em dinheiro, e é "
        "preciso ter caixa. O câmbio continua aberto, e a base local (a diferença entre o preço da sua "
        "região e o da bolsa) também. Contratos pouco negociados podem ter liquidez baixa.",
        "Quanto a base local e o câmbio vão andar até a colheita.",
    ),
    TextoDoInstrumento(
        "opcao",
        "Opção de venda (put)",
        "Paga um prêmio para ter o direito de vender pelo preço da trava, em dólar.",
        "Piso sem teto: se o preço cair, vale o preço da trava; se subir, fica com a alta.",
        "O prêmio é pago na hora e não volta, suba ou caia o preço. O câmbio e a base local continuam "
        "abertos.",
        "O prêmio de verdade no dia da compra; aqui entra o que você informou.",
    ),
    TextoDoInstrumento(
        "cpr",
        "CPR (Cédula de Produto Rural)",
        "Título em que o produtor promete entregar café (CPR física) ou pagar o valor dele (CPR "
        "financeira), muitas vezes recebendo dinheiro adiantado.",
        "Pode antecipar o dinheiro para o custeio da safra.",
        "É uma dívida: quebra de safra não tira a obrigação de entregar ou pagar, e o adiantamento tem "
        "custo financeiro.",
        "Ainda sem número nesta tela: a conta da CPR precisa do juro do período (CDI) e entra numa próxima "
        "versão.",
    ),
)
NOMES_DOS_INSTRUMENTOS = {i.chave: i.nome for i in INSTRUMENTOS}


# --- As tabelas da tela (o Streamlit e a futura rota mostram as mesmas linhas) ---


def _reais(valor: float | None) -> str:
    return "—" if valor is None else formatar_reais(valor)


def linhas_do_resumo(simulacao: trava.SimulacaoDaTrava) -> list[dict[str, str | int]]:
    """Uma linha por forma de travar, na ordem fixa da conta (nunca pelo resultado)."""
    return [
        {
            COLUNA_INSTRUMENTO: NOMES_DOS_INSTRUMENTOS[r.chave],
            COLUNA_MENOR: _reais(r.menor_margem),
            COLUNA_MEDIANA: _reais(r.mediana_da_margem),
            COLUNA_MAIOR: _reais(r.maior_margem),
            COLUNA_ABAIXO: f"{r.safras_abaixo_do_custo} de {r.safras}",
        }
        for r in simulacao.resumos
    ]


def linhas_das_safras(simulacao: trava.SimulacaoDaTrava) -> list[dict[str, str | int]]:
    """Uma linha por safra: os preços da trava e da colheita e a receita de cada forma de travar."""
    linhas = []
    for safra in simulacao.safras:
        linha: dict[str, str | int] = {
            COLUNA_SAFRA: safra.safra,
            COLUNA_TRAVA: f"{safra.mes_da_trava:%m/%Y}",
            COLUNA_COLHEITA: f"{safra.mes_da_colheita:%m/%Y}",
            COLUNA_PRECO_DA_TRAVA: _reais(safra.preco_da_trava),
            COLUNA_PRECO_NA_COLHEITA: _reais(safra.preco_na_colheita),
        }
        for instrumento in safra.instrumentos:
            linha[NOMES_DOS_INSTRUMENTOS[instrumento.chave]] = _reais(
                instrumento.receita_por_saca
            )
            if instrumento.pior_chamada_por_saca is not None:
                linha[COLUNA_CHAMADA] = _reais(instrumento.pior_chamada_por_saca)
        linhas.append(linha)
    return linhas


def explicacao_do_cenario(simulacao: trava.SimulacaoDaTrava) -> str:
    """A explicação dos cenários com o preço e o mês de hoje."""
    return EXPLICACAO_DO_CENARIO.format(
        preco=formatar_reais(simulacao.preco_de_hoje),
        mes=f"{simulacao.mes_do_preco_de_hoje:%m/%Y}",
    )
