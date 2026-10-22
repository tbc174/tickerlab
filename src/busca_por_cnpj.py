"""A busca por CNPJ (molde B, PR 2 do plano de 19/10/2026): o relatório de uma companhia aberta pelo CNPJ.

O relatório junta o cadastro da CVM (lido do banco do app na hora do pedido) com as seções da ficha da
noite (`src/dossie.py`, inclusive a `rede`), cada linha com a data e a fonte. No lançamento só as
companhias abertas com ficha: qualquer outro CNPJ recebe `FORA_DA_BASE_ABERTA`, a mesma resposta para
quem a base conhece (uma empresa fechada) e para quem não conhece. Nada é guardado: o pedido não fica em
lugar nenhum e o CNPJ pedido não vai para o log (o CNPJ de um MEI é dado pessoal, ADR 0077, item 1).
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import sqlalchemy as sa

from base import cnpj as cnpj_da_base
from base import dossie as dossie_da_base
from src import dossie
from src.banco.modelo import setores_cvm, tickers_dos_emissores
from src.contestacao import com_a_contestacao
from src.planos import DOSSIE_DA_BASE, motivo_sem_acesso
from src.relatorio_empresa import (
    CONVITE_DO_DOSSIE,
    FONTE_DO_SETOR,
    FONTE_DOS_TICKERS,
    FUSO,
    IDENTIFICACAO,
    TEXTO,
    Item,
    Secao,
    data_do_dossie,
    para_json,
)

Situacao = Literal["encontrada", "fora_da_base_aberta"]
ENCONTRADA: Situacao = "encontrada"
FORA: Situacao = "fora_da_base_aberta"

FILIAL_DA_MATRIZ = "0001"
TITULO_DO_CADASTRO = "Cadastro"
FONTE_DO_CADASTRO = (
    "cadastro de companhias abertas da CVM (razão social, setor e valores mobiliários)"
)
SECOES_DO_GRUPO_E_DA_REDE = ("auditor_e_controladas", "rede")

# a mesma frase para o CNPJ de empresa fechada e para o que a base nunca viu: não dizer qual é qual
FORA_DA_BASE_ABERTA = (
    "Este CNPJ ainda não está na base aberta do TickerLab. No lançamento a busca mostra só as "
    "companhias abertas."
)
DESLIGADO = (
    "Empresas fechadas: o relatório delas espera a licença dos dados da Receita Federal e da PGFN.",
    "Natureza jurídica e MEI: vêm da Receita Federal e esperam a mesma licença.",
    "Situação, categoria e data de registro na CVM: ainda não estão no banco do app.",
    "Dívida com a União, insolvência, situação especial e atrasos de pagamento: esperam um parecer jurídico.",
    "Sanções e dívidas entre empresas da rede: esperam um parecer jurídico.",
    "Sócios, administradores e qualquer nome de pessoa: não aparecem.",
    "Ligações de 2 ou mais saltos e busca por nome ou ticker: depois de medir o uso da busca.",
)
LIMITES_DA_BUSCA = (
    "Só as companhias abertas com ficha na base aparecem. Não aparecer aqui não quer dizer que a empresa não exista.",
    "O relatório é a ficha montada na noite indicada, não uma consulta em tempo real.",
    "Nada aqui é recomendação de investimento.",
)
AVISO_DA_FILIAL = (
    "O CNPJ pedido é de uma filial. O relatório é da matriz ({matriz}), a companhia que registra os "
    "documentos na CVM."
)


class PedidoInvalidoError(ValueError):
    """O texto não é um CNPJ (tamanho, caractere ou dígito verificador errado)."""


@dataclass(frozen=True)
class RelatorioDoCnpj:
    situacao: Situacao
    cnpj: str  # o pedido, ou o da matriz quando era uma filial
    empresa: str
    tickers: list[str]
    como_era_em: date | None  # o dia da ficha
    secoes: list[Secao]
    fontes: list[str]
    limites: list[str]
    desligado: list[str]
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return para_json(asdict(self))  # type: ignore[return-value]


def normalizar_pedido(texto: str) -> str:
    """Os 14 caracteres do CNPJ (com ou sem pontuação, com letras), com o dígito verificador conferido."""
    cnpj = cnpj_da_base.completo(texto)
    if cnpj is None or not cnpj_da_base.dv_confere(cnpj):
        raise PedidoInvalidoError(
            "Este não é um CNPJ válido: confira os 14 caracteres e os dois últimos dígitos."
        )
    return cnpj


def _matriz_da(cnpj: str) -> str:
    base = cnpj[: cnpj_da_base.TAMANHO_DA_RAIZ] + FILIAL_DA_MATRIZ
    return base + cnpj_da_base.digitos_verificadores(base)


def ficha_pela_raiz(
    cnpj: str, pasta: Path | None = None
) -> tuple[dossie.Ficha | None, str | None]:
    """A ficha do CNPJ ou, sendo filial, a da matriz (com o aviso); `(None, None)` sem ficha."""
    ficha = dossie.ficha_do(cnpj, pasta)
    if ficha is not None:
        return ficha, None
    matriz = _matriz_da(cnpj)
    if matriz == cnpj:
        return None, None
    ficha = dossie.ficha_do(matriz, pasta)
    if ficha is None:
        return None, None
    return ficha, AVISO_DA_FILIAL.format(matriz=cnpj_da_base.formatar(matriz))


def _item_do_cadastro(chave: str, nome: str, texto: str, base: str, fonte: str) -> Item:
    return Item(
        chave, nome, texto, None, TEXTO, base, fonte=fonte, sem_comparacao=IDENTIFICACAO
    )


def _dia(valor: date | datetime) -> date:
    if isinstance(valor, datetime):
        return (valor.astimezone(FUSO) if valor.tzinfo else valor).date()
    return valor


def secao_cadastro(conexao: sa.Connection, cnpj: str) -> Secao | None:
    """O cadastro da CVM no banco do app (razão social, setor e tickers); None se o CNPJ não está lá.

    Não traz a natureza jurídica nem a situação da Receita: a licença desses dados ainda não existe.
    """
    formatado = cnpj_da_base.formatar(cnpj)
    t = tickers_dos_emissores
    emissor = conexao.execute(
        sa.select(t.c.codigo, t.c.empresa, t.c.atualizado_em)
        .where(t.c.cnpj == formatado)
        .order_by(t.c.codigo)
    ).all()
    if not emissor:
        return None
    setor = conexao.execute(
        sa.select(setores_cvm.c.setor).where(setores_cvm.c.cnpj == formatado)
    ).scalar()
    dia = _dia(max(linha.atualizado_em for linha in emissor))
    base = f"cadastro da CVM em {dia:%d/%m/%Y}"
    itens = [
        _item_do_cadastro("cnpj", "CNPJ", formatado, base, FONTE_DO_CADASTRO),
        _item_do_cadastro(
            "razao_social", "Razão social", emissor[0].empresa, base, FONTE_DO_CADASTRO
        ),
    ]
    if setor:
        itens.append(_item_do_cadastro("setor", "Setor", setor, base, FONTE_DO_SETOR))
    codigos = ", ".join(sorted({linha.codigo for linha in emissor}))
    itens.append(
        _item_do_cadastro(
            "tickers", "Códigos de negociação", codigos, base, FONTE_DOS_TICKERS
        )
    )
    return Secao(
        "cadastro", TITULO_DO_CADASTRO, itens, [f"Fonte: {FONTE_DO_CADASTRO}."]
    )


def _ordem_da_ficha(secoes: list[Secao]) -> list[Secao]:
    """Grupo e rede logo depois do cadastro; os fatos na ordem da ficha (o setor é do molde D)."""
    primeiras = [
        s for chave in SECOES_DO_GRUPO_E_DA_REDE for s in secoes if s.chave == chave
    ]
    fora = {*SECOES_DO_GRUPO_E_DA_REDE, *dossie_da_base.SECOES_DO_MOLDE_D}
    return [*primeiras, *(s for s in secoes if s.chave not in fora)]


def _trancar(secoes: list[Secao], motivo: str) -> list[Secao]:
    convite = [f"{motivo} {CONVITE_DO_DOSSIE}"]
    return [Secao(s.chave, s.titulo, paragrafos=convite, trancada=True) for s in secoes]


def _tickers(cadastro: Secao | None) -> list[str]:
    itens = cadastro.itens if cadastro else []
    item = next((i for i in itens if i.chave == "tickers"), None)
    return item.texto.split(", ") if item else []


def montar_relatorio_do_cnpj(
    ficha: dossie.Ficha,
    cadastro: Secao | None,
    plano: str | None,
    hoje: date,
    aviso: str | None = None,
) -> RelatorioDoCnpj:
    """O relatório da companhia: cadastro (aberto), grupo, rede e fatos (trancados sem o plano)."""
    do_dossie = dossie.dossie_da_ficha(ficha, hoje)
    secoes = _ordem_da_ficha(do_dossie.secoes)
    motivo = motivo_sem_acesso(plano, DOSSIE_DA_BASE)
    if motivo is None:
        data = data_do_dossie(do_dossie)
        secoes = [replace(s, paragrafos=[data, *s.paragrafos]) for s in secoes]
    else:
        secoes = _trancar(secoes, motivo)
    fontes = list(do_dossie.fontes) if motivo is None else []
    if cadastro is not None:
        fontes.append(FONTE_DO_CADASTRO)
    return RelatorioDoCnpj(
        situacao=ENCONTRADA,
        cnpj=cnpj_da_base.formatar(ficha.cnpj),
        empresa=ficha.empresa,
        tickers=_tickers(cadastro),
        como_era_em=dossie.dia_da_ficha(ficha),
        secoes=[*([cadastro] if cadastro else []), *secoes],
        fontes=fontes,
        limites=com_a_contestacao([*LIMITES_DA_BUSCA, *do_dossie.limites]),
        desligado=list(DESLIGADO),
        avisos=[aviso] if aviso else [],
    )


def relatorio_fora_da_base_aberta(cnpj: str) -> RelatorioDoCnpj:
    """A resposta para qualquer CNPJ sem ficha: igual para a empresa fechada e para a desconhecida."""
    return RelatorioDoCnpj(
        situacao=FORA,
        cnpj=cnpj_da_base.formatar(cnpj),
        empresa="",
        tickers=[],
        como_era_em=None,
        secoes=[],
        fontes=[],
        limites=com_a_contestacao(list(LIMITES_DA_BUSCA)),
        desligado=list(DESLIGADO),
        avisos=[FORA_DA_BASE_ABERTA],
    )


def buscar_por_cnpj(
    conexao: sa.Connection,
    texto: str,
    plano: str | None,
    hoje: date | None = None,
    pasta: Path | None = None,
) -> RelatorioDoCnpj:
    """O pedido inteiro: confere o CNPJ, acha a ficha (ou a da matriz) e monta o relatório."""
    cnpj = normalizar_pedido(texto)
    ficha, aviso = ficha_pela_raiz(cnpj, pasta)
    if ficha is None:
        return relatorio_fora_da_base_aberta(cnpj)
    cadastro = secao_cadastro(conexao, ficha.cnpj)
    return montar_relatorio_do_cnpj(
        ficha, cadastro, plano, hoje or datetime.now(FUSO).date(), aviso
    )
