"""A busca por CNPJ (molde B, PR 2 do plano de 19/10/2026): o relatório de uma empresa pelo CNPJ.

Companhia aberta com ficha: o cadastro da CVM (lido do banco do app na hora do pedido) com as seções da ficha
da noite (`src/dossie.py`, inclusive a `rede`), cada linha com a data e a fonte. Empresa sem ficha na CVM
(PR 6 do plano da base de CNPJ com sócios, 20/10/2026): o cadastro da Receita, da vista do CNPJ publicada
no servidor (`src/cadastro_da_receita.py`, `src/relatorio_da_receita.py`). CNPJ que nenhuma das duas tem
recebe `FORA_DA_BASE_ABERTA`. Nada é guardado: o pedido não fica em lugar nenhum e o CNPJ pedido não vai
para o log (o CNPJ de um MEI é dado pessoal, ADR 0077, item 1).
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import sqlalchemy as sa

from base import cnpj as cnpj_da_base
from base import dossie as dossie_da_base
from base.pessoas.sem_cpf import tirar_cpf
from src import cadastro_da_receita, dossie
from src.banco.coletas import MOSTRAR, citacoes_das_fontes, exigir_licenca
from src.banco.modelo import setores_cvm, tickers_dos_emissores
from src.contestacao import com_a_contestacao
from src.planos import DOSSIE_DA_BASE, motivo_sem_acesso
from src.relatorio_da_receita import secoes_da_receita
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

Situacao = Literal["encontrada", "cadastro_da_receita", "fora_da_base_aberta"]
ENCONTRADA: Situacao = "encontrada"
CADASTRO_DA_RECEITA: Situacao = "cadastro_da_receita"  # empresa sem ficha na CVM
FORA: Situacao = "fora_da_base_aberta"
FONTE_DA_RECEITA = "rfb-cnpj"
ONDE_A_TRAVA_BARRA = "busca por CNPJ (cadastro da Receita)"

FILIAL_DA_MATRIZ = "0001"
TITULO_DO_CADASTRO = "Cadastro"
FONTE_DO_CADASTRO = (
    "cadastro de companhias abertas da CVM (razão social, setor, situação, categoria, registro e "
    "valores mobiliários)"
)
SECOES_DO_GRUPO_E_DA_REDE = ("auditor_e_controladas", "rede")

FORA_DA_BASE_ABERTA = "Este CNPJ não está na base do TickerLab. Não aparecer aqui não quer dizer que a empresa não exista."
DESLIGADO = (
    (
        "Razão social e natureza jurídica das empresas fechadas: esperam a leitura do arquivo de empresas da "
        "Receita Federal."
    ),
    (
        "Motivo da situação cadastral e situação especial (como falência e recuperação judicial): ficam de fora "
        "até a natureza jurídica separar o MEI e o empresário individual, que não recebem sinal negativo."
    ),
    "Dívida com a União e atrasos de pagamento: esperam um parecer jurídico.",
    "Sanções e dívidas entre empresas da rede: esperam um parecer jurídico.",
    (
        "Nome de sócio ou administrador pessoa física: não aparece; a linha mostra só a qualificação e o mês "
        "de entrada."
    ),
    "Endereço: só o município e a UF; telefone e e-mail nunca aparecem.",
    "Ligações de 2 ou mais saltos e busca por nome ou ticker: depois de medir o uso da busca.",
)
QUEM_APARECE = (
    "Aparecem as companhias abertas com ficha na base e as empresas do cadastro aberto do CNPJ da Receita "
    "Federal. Não aparecer aqui não quer dizer que a empresa não exista."
)
NAO_E_RECOMENDACAO = "Nada aqui é recomendação de investimento."
LIMITES_DA_BUSCA = (
    QUEM_APARECE,
    "O relatório é a ficha montada na noite indicada, não uma consulta em tempo real.",
    NAO_E_RECOMENDACAO,
)
LIMITES_DA_RECEITA = (  # a empresa sem ficha: não há ficha da noite, há a publicação do mês
    QUEM_APARECE,
    (
        "O cadastro é o da publicação mensal da Receita indicada em cada linha, não uma consulta em tempo "
        "real: a empresa pode ter mudado depois dela."
    ),
    NAO_E_RECOMENDACAO,
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


def _base_do_cadastro(dia: date) -> str:
    return f"cadastro da CVM em {dia:%d/%m/%Y}"


def _situacao_por_extenso(situacao: str, desde: date | None) -> str:
    """`ATIVO` + 2001-05-10 → "Ativo, desde 10/05/2001" (a situação muda: a data vai junto)."""
    texto = situacao.capitalize()
    return f"{texto}, desde {desde:%d/%m/%Y}" if desde else texto


def _itens_do_registro(registro: sa.Row | None, base: str) -> list[Item]:
    """Setor, situação, categoria e data de registro na CVM, cada um só quando o banco tem."""
    if registro is None:
        return []
    dia = _dia(registro.atualizado_em) if registro.atualizado_em else None
    base_do_registro = _base_do_cadastro(dia) if dia else base
    itens = []
    if registro.setor:
        itens.append(
            _item_do_cadastro("setor", "Setor", registro.setor, base, FONTE_DO_SETOR)
        )
    if registro.situacao:
        texto = _situacao_por_extenso(registro.situacao, registro.situacao_desde)
        itens.append(
            _item_do_cadastro(
                "situacao",
                "Situação na CVM",
                texto,
                base_do_registro,
                FONTE_DO_CADASTRO,
            )
        )
    if registro.categoria:
        itens.append(
            _item_do_cadastro(
                "categoria",
                "Categoria de registro",
                registro.categoria,
                base_do_registro,
                FONTE_DO_CADASTRO,
            )
        )
    if registro.registro:
        itens.append(
            _item_do_cadastro(
                "registro",
                "Registro na CVM",
                f"{registro.registro:%d/%m/%Y}",
                base_do_registro,
                FONTE_DO_CADASTRO,
            )
        )
    return itens


def secao_cadastro(conexao: sa.Connection, cnpj: str) -> Secao | None:
    """O cadastro da CVM no banco do app (razão social, setor, situação, categoria, registro e
    tickers); None se o CNPJ não está lá.

    Não traz a natureza jurídica nem a situação da Receita: estas vêm só para a empresa sem ficha.
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
    registro = conexao.execute(
        sa.select(setores_cvm).where(setores_cvm.c.cnpj == formatado)
    ).first()
    dia = _dia(max(linha.atualizado_em for linha in emissor))
    base = _base_do_cadastro(dia)
    itens = [
        _item_do_cadastro("cnpj", "CNPJ", formatado, base, FONTE_DO_CADASTRO),
        _item_do_cadastro(
            "razao_social",
            "Razão social",
            tirar_cpf(emissor[0].empresa),
            base,
            FONTE_DO_CADASTRO,
        ),
        *_itens_do_registro(registro, base),
    ]
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


def montar_relatorio_da_fechada(
    cadastro: cadastro_da_receita.CadastroDaReceita, cnpj: str, plano: str | None
) -> RelatorioDoCnpj:
    """O relatório da empresa sem ficha na CVM: o cadastro (aberto) e o resto (trancado sem o plano)."""
    exigir_licenca(MOSTRAR, [FONTE_DA_RECEITA], onde=ONDE_A_TRAVA_BARRA)
    cadastro_aberto, *resto = secoes_da_receita(cadastro, cnpj)
    motivo = motivo_sem_acesso(plano, DOSSIE_DA_BASE)
    if motivo is not None:
        resto = _trancar(resto, motivo)
    return RelatorioDoCnpj(
        situacao=CADASTRO_DA_RECEITA,
        cnpj=cnpj_da_base.formatar(cnpj),
        empresa="",  # a razão social espera o arquivo de empresas da Receita
        tickers=[],
        como_era_em=cadastro.disponivel_em,
        secoes=[cadastro_aberto, *resto],
        fontes=citacoes_das_fontes([FONTE_DA_RECEITA]),
        limites=com_a_contestacao(list(LIMITES_DA_RECEITA)),
        desligado=list(DESLIGADO),
    )


def relatorio_fora_da_base_aberta(cnpj: str) -> RelatorioDoCnpj:
    """A resposta para o CNPJ que nem a CVM nem o cadastro da Receita da base têm."""
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
    vista: Path | None = None,
) -> RelatorioDoCnpj:
    """O pedido inteiro: confere o CNPJ, acha a ficha (ou a da matriz) ou o cadastro da Receita e monta o
    relatório."""
    cnpj = normalizar_pedido(texto)
    ficha, aviso = ficha_pela_raiz(cnpj, pasta)
    if ficha is None:
        cadastro = cadastro_da_receita.cadastro_do_cnpj(cnpj, vista)
        if cadastro is None:
            return relatorio_fora_da_base_aberta(cnpj)
        return montar_relatorio_da_fechada(cadastro, cnpj, plano)
    cadastro = secao_cadastro(conexao, ficha.cnpj)
    return montar_relatorio_do_cnpj(
        ficha, cadastro, plano, hoje or datetime.now(FUSO).date(), aviso
    )
