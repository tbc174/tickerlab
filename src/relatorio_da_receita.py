"""As seções do relatório de uma empresa fechada na busca por CNPJ, a partir do cadastro da Receita.

Cinco seções, cada linha com a fonte e o mês da publicação: o cadastro do estabelecimento pedido, o Simples e
o MEI, o quadro de sócios, os estabelecimentos e o que mudou nos últimos 12 meses. O que fica de fora e por
quê está no `DESLIGADO` da busca: razão social e natureza jurídica (a base ainda não lê o arquivo de empresas
da Receita), motivo da situação e situação especial (sinal negativo de MEI e empresário individual) e o nome
de sócio pessoa física (portão fechado).
"""

from typing import Any

import pandas as pd

from base import cnpj as cnpj_da_base
from base import receita_codigos as codigos
from src.banco.coletas import FRASE_DA_RECEITA
from src.cadastro_da_receita import CadastroDaReceita
from src.relatorio_empresa import IDENTIFICACAO, TEXTO, Item, Secao

QUANTOS_ESTABELECIMENTOS = 20
QUANTOS_SOCIOS = 50
QUANTAS_MUDANCAS = 50
SITUACAO_ATIVA = "02"
SOCIO_PESSOA_JURIDICA, SOCIO_PESSOA_FISICA, SOCIO_ESTRANGEIRO = "1", "2", "3"
ENTROU, SAIU = "entrou", "saiu"
SETA = " → "
SEM_SOCIOS = "A Receita não publica quadro de sócios para esta empresa (é o caso do MEI e do empresário individual)."
SEM_MUDANCAS = "Nenhuma mudança no cadastro, no Simples ou nos sócios nos últimos 12 meses publicados."
SOCIO_SEM_NOME = (
    "O sócio pessoa física aparece sem o nome: só a qualificação e o mês de entrada."
)


def _dia(valor: object) -> str | None:
    return None if pd.isna(valor) else f"{pd.Timestamp(valor):%d/%m/%Y}"


def _mes(valor: object) -> str | None:
    return None if pd.isna(valor) else f"{pd.Timestamp(valor):%m/%Y}"


def _mes_da_publicacao(mes: str) -> str:
    """`2024-09` → "09/2024"."""
    return f"{mes[5:]}/{mes[:4]}"


def _raiz_formatada(raiz: str) -> str:
    return f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:8]}"


def _situacao(codigo: str | None, desde: object) -> str:
    """ "Ativa, desde 01/02/2010" (a situação muda: a data vai junto)."""
    nome = codigos.situacao_cadastral(codigo) or "não informada"
    dia = _dia(desde)
    return f"{nome}, desde {dia}" if dia else nome


def _local(municipio: str | None, uf: str | None) -> str:
    partes = [codigos.municipio(municipio), (uf or "").strip() or None]
    return "/".join(p for p in partes if p) or "não informado"


def _atividade(codigo: str | None, com_o_codigo: bool = True) -> str:
    nome = codigos.cnae(codigo)
    if nome is None:
        return "não informada"
    if not com_o_codigo:
        return nome
    c = str(codigo).strip().zfill(7)
    return f"{nome} (CNAE {c[:4]}-{c[4]}/{c[5:]})"


def _item(chave: str, nome: str, texto: str, base: str) -> Item:
    return Item(
        chave,
        nome,
        texto,
        None,
        TEXTO,
        base,
        fonte=FRASE_DA_RECEITA,
        sem_comparacao=IDENTIFICACAO,
    )


def _paragrafo_da_fonte(cadastro: CadastroDaReceita) -> str:
    return f"{FRASE_DA_RECEITA}, publicação de {_mes_da_publicacao(cadastro.mes)}."


def _com_o_limite(linhas: list[dict], limite: int) -> tuple[list[dict], list[str]]:
    if len(linhas) <= limite:
        return linhas, []
    return linhas[:limite], [
        f"E mais {len(linhas) - limite} linhas: a tabela mostra as {limite} primeiras."
    ]


def secao_do_cadastro(cadastro: CadastroDaReceita, cnpj: str, base: str) -> Secao:
    """O estabelecimento pedido: situação, início, atividade e município (nunca o endereço fino)."""
    todos = cadastro.estabelecimentos
    pedido = todos[todos["cnpj"] == cnpj].iloc[0]
    ativos = int((todos["situacao_cadastral"] == SITUACAO_ATIVA).sum())
    plural = "ativo" if ativos == 1 else "ativos"
    itens = [
        _item("cnpj", "CNPJ", cnpj_da_base.formatar(cnpj), base),
        _item(
            "situacao",
            "Situação cadastral",
            _situacao(pedido["situacao_cadastral"], pedido["data_situacao_cadastral"]),
            base,
        ),
        _item(
            "inicio_atividade",
            "Início da atividade",
            _dia(pedido["data_inicio_atividade"]) or "não informado",
            base,
        ),
        _item(
            "atividade",
            "Atividade principal",
            _atividade(pedido["cnae_principal"]),
            base,
        ),
        _item("local", "Município", _local(pedido["municipio"], pedido["uf"]), base),
        _item(
            "estabelecimentos",
            "Estabelecimentos",
            f"{len(todos)} ({ativos} {plural})",
            base,
        ),
    ]
    return Secao(
        "cadastro_da_receita",
        "Cadastro na Receita Federal",
        itens,
        [_paragrafo_da_fonte(cadastro)],
    )


def _texto_do_simples(linha: dict | None) -> str:
    if linha is None:
        return "Sem registro no Simples Nacional"
    if linha["optante_simples"]:
        return f"Optante desde {_dia(linha['data_opcao_simples'])}"
    saida = _dia(linha["data_exclusao_simples"])
    return f"Não optante (saiu em {saida})" if saida else "Não optante"


def _texto_do_mei(linha: dict | None) -> str:
    if linha is None:
        return "Não"
    if linha["optante_mei"]:
        return f"Sim, desde {_dia(linha['data_opcao_mei'])}"
    saida = _dia(linha["data_exclusao_mei"])
    return f"Não (deixou de ser MEI em {saida})" if saida else "Não"


def secao_do_simples(cadastro: CadastroDaReceita, base: str) -> Secao:
    itens = [
        _item("simples", "Simples Nacional", _texto_do_simples(cadastro.simples), base),
        _item("mei", "MEI", _texto_do_mei(cadastro.simples), base),
    ]
    return Secao(
        "simples_e_mei",
        "Simples Nacional e MEI",
        itens,
        [_paragrafo_da_fonte(cadastro)],
    )


def _quem(
    tipo_socio: str,
    raiz_socio_pj: str | None,
    pais: str | None,
    nome: str | None = None,
) -> str:
    """Quem é o sócio sem dizer o nome da pessoa física (o nome só vem do portão aberto)."""
    if nome:
        return str(nome)
    if tipo_socio == SOCIO_PESSOA_JURIDICA and raiz_socio_pj:
        return f"pessoa jurídica {_raiz_formatada(raiz_socio_pj)}"
    if tipo_socio == SOCIO_ESTRANGEIRO:
        lugar = codigos.pais(pais)
        return f"sócio estrangeiro ({lugar})" if lugar else "sócio estrangeiro"
    return "sócio pessoa física"


def _qualificacao(codigo: str | None) -> str:
    return (codigos.qualificacao(codigo) or "não informada").lower()


def secao_dos_socios(cadastro: CadastroDaReceita) -> Secao:
    socios = cadastro.socios.sort_values(
        ["data_entrada", "tipo_socio"], na_position="last", kind="stable"
    )
    linhas = [
        {
            "socio": _quem(s.tipo_socio, s.raiz_socio_pj, s.pais, s.nome),
            "qualificacao": _qualificacao(s.qualificacao),
            "desde": _mes(s.data_entrada) or "não informado",
        }
        for s in socios.itertuples()
    ]
    linhas, resto = _com_o_limite(linhas, QUANTOS_SOCIOS)
    paragrafos = [_paragrafo_da_fonte(cadastro)]
    if not linhas:
        paragrafos.append(SEM_SOCIOS)
    elif (socios["tipo_socio"] == SOCIO_PESSOA_FISICA).any():
        paragrafos.append(SOCIO_SEM_NOME)
    return Secao(
        "socios_da_receita",
        "Quadro de sócios",
        paragrafos=[*paragrafos, *resto],
        tabelas={"socios_da_receita": linhas} if linhas else {},
    )


def secao_dos_estabelecimentos(cadastro: CadastroDaReceita) -> Secao:
    linhas = [
        {
            "cnpj": cnpj_da_base.formatar(e.cnpj),
            "tipo": "matriz" if e.matriz else "filial",
            "situacao": _situacao(e.situacao_cadastral, e.data_situacao_cadastral),
            "inicio": _dia(e.data_inicio_atividade) or "não informado",
            "atividade": _atividade(e.cnae_principal, com_o_codigo=False),
            "local": _local(e.municipio, e.uf),
        }
        for e in cadastro.estabelecimentos.itertuples()
    ]
    linhas, resto = _com_o_limite(linhas, QUANTOS_ESTABELECIMENTOS)
    return Secao(
        "estabelecimentos",
        "Estabelecimentos",
        paragrafos=[_paragrafo_da_fonte(cadastro), *resto],
        tabelas={"estabelecimentos": linhas},
    )


def _mudancas_de_estabelecimento(linha: Any) -> str:  # noqa: ANN401 (linha do itertuples)
    if linha.tipo == ENTROU:
        return "entrou no cadastro"
    if linha.tipo == SAIU:
        return "saiu do cadastro"
    partes = []
    if linha.situacao_cadastral_antes != linha.situacao_cadastral_depois:
        antes = codigos.situacao_cadastral(linha.situacao_cadastral_antes)
        depois = codigos.situacao_cadastral(linha.situacao_cadastral_depois)
        partes.append(f"situação: {antes}{SETA}{depois}")
    if linha.cnae_principal_antes != linha.cnae_principal_depois:
        antes = _atividade(linha.cnae_principal_antes, com_o_codigo=False)
        depois = _atividade(linha.cnae_principal_depois, com_o_codigo=False)
        partes.append(f"atividade: {antes}{SETA}{depois}")
    local_antes = _local(linha.municipio_antes, linha.uf_antes)
    local_depois = _local(linha.municipio_depois, linha.uf_depois)
    if local_antes != local_depois:
        partes.append(f"município: {local_antes}{SETA}{local_depois}")
    return "; ".join(partes)


def _mudancas_do_simples(linha: Any) -> str:  # noqa: ANN401 (linha do itertuples)
    if linha.tipo == SAIU:
        return "saiu do registro do Simples"
    partes = []
    for campo, passou, deixou in (
        ("optante_simples", "passou a optar pelo Simples", "deixou o Simples"),
        ("optante_mei", "passou a ser MEI", "deixou de ser MEI"),
    ):
        antes = bool(getattr(linha, f"{campo}_antes")) and linha.tipo != ENTROU
        depois = bool(getattr(linha, f"{campo}_depois"))
        if antes != depois:
            partes.append(passou if depois else deixou)
    return "; ".join(partes) or "entrou no registro do Simples"


def _mudancas_de_socio(linha: Any) -> str:  # noqa: ANN401 (linha do itertuples)
    quem = _quem(linha.tipo_socio, linha.raiz_socio_pj, None)
    if linha.tipo == ENTROU:
        return f"entrou: {quem}, {_qualificacao(linha.qualificacao_depois)}"
    if linha.tipo == SAIU:
        return f"saiu: {quem}, {_qualificacao(linha.qualificacao_antes)}"
    partes = []
    if linha.qualificacao_antes != linha.qualificacao_depois:
        antes = _qualificacao(linha.qualificacao_antes)
        depois = _qualificacao(linha.qualificacao_depois)
        partes.append(f"{quem}: qualificação {antes}{SETA}{depois}")
    if _mes(linha.data_entrada_antes) != _mes(linha.data_entrada_depois):
        antes, depois = _mes(linha.data_entrada_antes), _mes(linha.data_entrada_depois)
        partes.append(f"{quem}: entrada {antes}{SETA}{depois}")
    return "; ".join(partes)


def _linhas_de_mudanca(cadastro: CadastroDaReceita) -> list[dict]:
    """As mudanças das três tabelas, das mais novas para as mais velhas (no mesmo mês, na ordem
    estabelecimentos, Simples, sócios)."""
    descrever = {
        "estabelecimentos": (
            _mudancas_de_estabelecimento,
            lambda linha: f"estabelecimento {cnpj_da_base.formatar(linha.cnpj)}",
        ),
        "simples": (_mudancas_do_simples, lambda _: "Simples e MEI"),
        "qsa": (_mudancas_de_socio, lambda _: "sócios"),
    }
    linhas = []
    for tabela, (mudanca, onde) in descrever.items():
        dados = cadastro.mudancas.get(tabela, pd.DataFrame())
        for linha in dados.itertuples():
            texto = mudanca(linha)
            if texto:
                linhas.append({"mes": linha.mes, "onde": onde(linha), "mudanca": texto})
    # a ordenação é estável: no mesmo mês, a ordem das tabelas fica
    linhas.sort(key=lambda linha: linha["mes"], reverse=True)
    return [linha | {"mes": _mes_da_publicacao(linha["mes"])} for linha in linhas]


def secao_das_mudancas(cadastro: CadastroDaReceita) -> Secao:
    linhas, resto = _com_o_limite(_linhas_de_mudanca(cadastro), QUANTAS_MUDANCAS)
    paragrafos = [_paragrafo_da_fonte(cadastro), *resto]
    if not linhas:
        paragrafos.append(SEM_MUDANCAS)
    return Secao(
        "mudancas_da_receita",
        "O que mudou nos últimos 12 meses",
        paragrafos=paragrafos,
        tabelas={"mudancas_da_receita": linhas} if linhas else {},
    )


def secoes_da_receita(cadastro: CadastroDaReceita, cnpj: str) -> list[Secao]:
    """As cinco seções da empresa fechada; a primeira (o cadastro) é aberta a todos os planos."""
    base = f"dados abertos do CNPJ de {_mes_da_publicacao(cadastro.mes)}"
    return [
        secao_do_cadastro(cadastro, cnpj, base),
        secao_do_simples(cadastro, base),
        secao_dos_socios(cadastro),
        secao_dos_estabelecimentos(cadastro),
        secao_das_mudancas(cadastro),
    ]
