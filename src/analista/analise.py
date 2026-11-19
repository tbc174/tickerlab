"""A análise completa na ficha do analista (19/11/2026): a mesma montagem da rota `/analysis`, pelo portão da tela.

A tela não faz conta nova: chama `montar_analise` (`src/api_externa/conjuntos/analise.py`), a mesma da rota
`GET /data/v1/companies/{cnpj}/analysis` e da ferramenta `analise_completa` do conector, com o portão da ficha
(`leitura.permitido_na_tela`: o da API externa, campo a campo, sem o contrato da organização). Quem entra é a conta
com login e o plano da página da ficha; o analista vê só o que uma chave veria pela API.

Na leitura mais estreita, a tela abre só os blocos de finalidade **análise**: o bloco de crédito (finalidade crédito,
"dossiê e monitoramento") tem contrato próprio na API e aqui sai como "não disponível nesta tela", com os itens que a
análise não consulta para ninguém (sanções, ambiente, lista suja, dívida ativa, contratos públicos, processos e
pessoas físicas). **Sem pessoa:** a montagem só lê empresa e sócio pessoa jurídica; o bloco de pessoas, com a
permissão `pessoa_na_tela`, fica para outro PR.

Os estados são os da ficha (`leitura`): `pronta`; `nao_liberada` (nenhum cadastro aberto pelo portão: decide-se sem
ler o CNPJ); `nao_disponivel` (o CNPJ não é servido: não existe, é pessoa, MEI ou empresário individual), sem dizer o
motivo. Os nomes de bloco voltam do nome de fora (o da API) para o da tela, com o título e o que o bloco traz, e os
limites trocam o nome de campo de quem programa pela frase da tela. O que sai pela prontidão de piloto leva o aviso
(`leitura.com_aviso_de_piloto`), como a ficha.
"""

from collections.abc import Iterable
from datetime import date

from base import cnpj as cnpj_
from base.porta import Porta
from src.analista import leitura, vinculos
from src.api_externa.conjuntos import analise as analise_
from src.api_externa.envelope import fontes_da_resposta
from src.api_externa.nomes import para_fora
from src.portao_externo import (
    Canal,
    Finalidade,
    Pedido,
    Regras,
    decidir,
    regras_vigentes,
)

# a lista inteira de cada bloco está na aba dele na ficha; a análise é o resumo, como na API
LINHAS_POR_BLOCO = analise_.LINHAS_POR_BLOCO
NAO_DISPONIVEL_NA_TELA = "não disponível nesta tela"
CREDITO_NAO_DISPONIVEL = (
    "Fatos de crédito (dívida e pagamentos ao poder público): não disponível nesta tela"
)

# (título, o que traz) de cada bloco, na voz da tela; há teste que cobra um título para cada bloco da montagem
TITULOS: dict[str, tuple[str, str]] = {
    analise_.CADASTRO: (
        "Cadastro",
        "Receita Federal: razão social, situação, atividade, sede e início; da companhia aberta, as entregas à CVM.",
    ),
    "socios_pj": (
        "Grupo e sócios pessoa jurídica",
        "Receita Federal: as empresas sócias desta e as empresas de que esta é sócia (só pessoa jurídica).",
    ),
    "vinculos": (
        "Controle, coligação e auditoria",
        "CVM (FRE e FCA): quem controla, quem é controlada ou coligada e a firma que audita.",
    ),
    "eventos": (
        "Eventos",
        "CVM: fatos relevantes, comunicados e trocas de auditor.",
    ),
    "credito": ("Crédito", "Fatos de crédito ligados ao CNPJ."),
    "ativos": (
        "Ativos",
        "Bens e autorizações ligados ao CNPJ nas bases públicas.",
    ),
    "comparaveis": (
        "Comparáveis",
        "CVM: companhias do mesmo grupo de setores.",
    ),
    "regulados": (
        "Atividades reguladas",
        "Agências reguladoras: registros e autorizações da empresa.",
    ),
    "balanco_no_bc": (
        "Balanço no Banco Central",
        "Banco Central: os números da instituição autorizada.",
    ),
    "administradora_de_fii": (
        "Fundos que administra",
        "CVM: fundos imobiliários de que a empresa é a administradora.",
    ),
}

# os limites da montagem falam do campo da API (ainda_nao_traz, truncated) e da organização; a tela tem os dela
LIMITES_DA_TELA = {
    analise_.LIMITES[0]: (
        "A análise junta os blocos que a tela pode mostrar, cada um lido como na aba dele e pelo mesmo portão; "
        "bloco que não aparece não foi consultado, e isso não diz nada sobre a empresa."
    ),
    analise_.LIMITES[1]: (
        'O que está em "Não disponível nesta tela" não foi consultado: a ausência não quer dizer que a empresa '
        "não tem registro nessas bases."
    ),
    analise_.LIMITES[3]: (
        f"Cada bloco traz até {LINHAS_POR_BLOCO} linhas por lista; a aba do bloco na ficha traz o resto."
    ),
}
# os limites das respostas sem análise (não liberada, não disponível): os da montagem, na voz da tela
LIMITES = tuple(LIMITES_DA_TELA.get(limite, limite) for limite in analise_.LIMITES)
AVISOS_DA_TELA = {
    **leitura.AVISOS_DA_TELA,
    **vinculos.AVISOS_DA_TELA,
    **LIMITES_DA_TELA,
}
# o nome de fora (o da API) de volta ao da tela
_DE_FORA = {
    para_fora(bloco.nome): bloco.nome
    for bloco in (*analise_.CADASTROS, *analise_.BLOCOS)
}


def liberadas_na_tela(
    hoje: date, regras: Regras, *, piloto: bool = False
) -> set[analise_.Liberada]:
    """(conjunto, finalidade, fonte, campo) de cada linha que o portão da tela libera hoje, só de análise: é o que
    abre os blocos, antes de ler a empresa. Não registra o piloto (quem marca o aviso é a leitura dos campos)."""
    return {
        (linha.conjunto, linha.finalidade.value, linha.fonte, linha.campo)
        for linha in regras.linhas
        if linha.canal == Canal.API_EXTERNA
        and linha.finalidade == Finalidade.ANALISE
        and decidir(
            Pedido(
                fonte=linha.fonte,
                conjunto=linha.conjunto,
                campo=linha.campo,
                canal=Canal.API_EXTERNA,
                finalidade=Finalidade.ANALISE,
                piloto=piloto,
            ),
            hoje,
            regras,
        ).libera
    }


def analise(
    porta: Porta,
    cnpj: str,
    *,
    hoje: date,
    regras: Regras | None = None,
    piloto: bool = False,
) -> leitura.Resposta:
    """A análise completa do CNPJ como era hoje, pela montagem da API e pelo portão da tela.

    `piloto`: a conta é de uma organização com a marca de piloto (D11, conferido pela rota no servidor).
    `ValueError` se o CNPJ é inválido (a rota responde 422)."""
    numeros = cnpj_.normalizar_cnpj(cnpj)
    if not numeros:
        raise ValueError("CNPJ inválido")
    return leitura.com_aviso_de_piloto(
        lambda: _sem_aviso(porta, numeros, hoje, regras, piloto)
    )


def _sem_aviso(
    porta: Porta, cnpj: str, hoje: date, regras: Regras | None, piloto: bool
) -> leitura.Resposta:
    regras = regras or regras_vigentes()
    liberadas = liberadas_na_tela(hoje, regras, piloto=piloto)
    if analise_.blocos_abertos(liberadas)[0] is None:
        return leitura.Resposta(leitura.NAO_LIBERADA)
    servida = analise_.montar_analise(
        cnpj,
        hoje,
        porta=porta,
        liberadas=liberadas,
        portao=lambda conjunto, _: leitura.permitido_na_tela(
            conjunto, hoje, regras, piloto=piloto
        ),
        linhas=LINHAS_POR_BLOCO,
    )
    if servida is None or not servida.corpo:
        return leitura.Resposta(leitura.NAO_DISPONIVEL)
    return leitura.Resposta(
        leitura.PRONTA,
        corpo_da_tela(servida.corpo),
        fontes_da_resposta(servida.fontes),
        servida.linhas,
    )


def _da_tela(nome_de_fora: object) -> str:
    return _DE_FORA.get(str(nome_de_fora), str(nome_de_fora))


def _titulo(nome: str) -> str:
    return TITULOS.get(nome, (nome, ""))[0]


def _com_bloco_da_tela(itens: Iterable[dict], chave_do_titulo: str) -> list[dict]:
    lista = []
    for item in itens:
        nome = _da_tela(item.get("bloco"))
        lista.append({**item, "bloco": nome, chave_do_titulo: _titulo(nome)})
    return lista


def _ainda_nao_traz(textos: Iterable[str]) -> list[str]:
    na_tela = [
        texto.replace(analise_.NAO_DISPONIVEL_NESTA_CHAVE, NAO_DISPONIVEL_NA_TELA)
        for texto in textos
    ]
    return [CREDITO_NAO_DISPONIVEL, *na_tela]


def corpo_da_tela(corpo: dict) -> dict:
    """O corpo da montagem na voz da tela: blocos em lista, na ordem, com título; nomes de bloco da tela nas
    listas; o que a análise não consulta dito para a tela; limites sem nome de campo da API."""
    blocos = [
        {
            "nome": nome,
            "titulo": TITULOS.get(nome, (nome, ""))[0],
            "o_que_traz": TITULOS.get(nome, ("", ""))[1],
            "corpo": dentro,
        }
        for nome, dentro in corpo["blocos"].items()
    ]
    return {
        "cnpj": corpo["cnpj"],
        "como_era_em": corpo["como_era_em"],
        "frase": {
            **corpo["frase"],
            "a_partir_de": [analise_.CADASTRO],  # a frase é só do cadastro
        },
        "blocos": blocos,
        "linha_do_tempo": _com_bloco_da_tela(
            corpo["linha_do_tempo"], "titulo_do_bloco"
        ),
        "leituras": [
            {**item, "a_partir_de": [_da_tela(n) for n in item["a_partir_de"]]}
            for item in corpo["leituras"]
        ],
        "nao_encontrado": _com_bloco_da_tela(corpo["nao_encontrado"], "titulo"),
        "nao_respondeu_a_tempo": _com_bloco_da_tela(
            corpo["nao_respondeu_a_tempo"], "titulo"
        ),
        "ainda_nao_traz": _ainda_nao_traz(corpo["ainda_nao_traz"]),
        "limites": list(leitura.limites_da_tela(corpo["limites"], AVISOS_DA_TELA)),
    }
