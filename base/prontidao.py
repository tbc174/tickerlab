"""Prontidão de cada tabela para a API externa (ADR 0108, Emenda 1, D10).

A API externa só serve tabela **pronta**: que passou nas exigências 6 (conferência cruzada), 7
(qualidade automática) e 8 (dicionário) da ADR 0027, na régua de vender (Emenda 2 da 0027). Este
módulo é a fonte única desse registro, escrito à mão: por tabela, a data e a prova de cada exigência e
a versão maior do contrato que foi conferida. O portão (`src/portao_externo.py`) nega o que não
estiver aqui; o catálogo (`base/contrato.py`) mostra o registro de cada tabela pronta.

Quem grava (D10.5): **tirar** uma tabela daqui é nível 3 (o placar ficou vermelho, achou-se um erro);
**dar** prontidão é nível 2 da mesa Dados, só com as três provas e, na da 8, a data e as palavras da
revisão do dicionário. A prova é um identificador curto, sem caminho, IP, endereço ou e-mail: o
catálogo também vai para o site público.
"""

import os
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from functools import cache
from typing import NamedTuple

# D10.4: o placar (linha 427) renova a 6 e a 7; prova mais velha que isto já não vale
PRAZO_DA_PROVA = timedelta(days=90)
# o que não pode aparecer numa prova publicada: caminho, endereço, IPv4 e e-mail
_FORA_DA_PROVA = re.compile(r"[/\\@]|https?:|\b\d{1,3}(?:\.\d{1,3}){3}\b")


class Prova(NamedTuple):
    """Uma exigência cumprida: em que dia e o que prova. `independencia` só na 6: por que as duas
    fontes são independentes, ou qual é o par "mesmo documento, outro canal" (D10.6)."""

    data: date
    prova: str
    independencia: str = ""


class Prontidao(NamedTuple):
    """As três provas de uma tabela e a versão maior do contrato conferida. Vazio = falta."""

    versao_maior: int
    cruzada: Prova | None  # exigência 6
    qualidade: Prova | None  # exigência 7
    dicionario: Prova | None  # exigência 8


class Falta(StrEnum):
    """Por que a tabela não está pronta (os mesmos valores do `Motivo` do portão, para o log)."""

    SEM_TABELA = "sem_tabela"  # a linha de direito não diz de que tabela o campo sai
    SEM_PRONTIDAO = (
        "sem_prontidao"  # sem registro, ou alguma exigência sem data e prova
    )
    PRONTIDAO_VENCIDA = "prontidao_vencida"  # prova da 6 ou da 7 com mais de 90 dias
    CONTRATO_MUDOU = "contrato_mudou"  # versão maior diferente da conferida


# Só entra tabela com as três provas (D10.5). As provas da 6 e da 7 vêm do placar e vencem em 90 dias.
PRONTIDAO: dict[str, Prontidao] = {
    "demonstracoes_como_era": Prontidao(
        versao_maior=3,
        cruzada=Prova(
            data=date(2026, 11, 12),
            prova=(
                "DFP e ITR lidos da base contra o mesmo documento no ENET, em amostras sorteadas "
                "(a data da prova é a da DFP, em 12 de novembro de 2026): DFP 16055 valores comparados, "
                "16055 iguais, nenhum diferente; ITR (14 de novembro de 2026, três trimestres de 2025, 60 de 60 "
                "pacotes lidos) 29310 valores comparados, 29310 iguais, nenhum diferente; ficaram sem par 123 valores da base (zeros da conta 3.99 da DRE, que o ENET entrega em branco) "
                "e 186181 do ENET (183151 zeros e 3030 de contas que a base não guarda ou guarda em outro período), "
                "e nenhum desses entra na conta de iguais nem na de diferentes"
            ),
            independencia=(
                "mesmo documento, outro canal: a base lê os dados abertos da CVM "
                "e a conferência baixa o XML da entrega no ENET"
            ),
        ),
        qualidade=Prova(
            data=date(2026, 11, 12),
            prova=(
                "placar de qualidade verde em 24328845 linhas: chave única, colunas "
                "obrigatórias preenchidas, 2 achados todos explicados"
            ),
        ),
        dicionario=Prova(
            data=date(2026, 11, 14),
            prova=(
                "dicionário lido pelo dono do projeto em 14 de novembro de 2026, leitura própria e só "
                "deste dicionário: resultado lido, sem correção pendente"
            ),
        ),
    ),
}


def versao_maior(versao: str) -> int:
    """O primeiro número de "maior.menor.correção"."""
    return int(versao.split(".", 1)[0])


@cache
def versoes_maiores() -> Mapping[str, int]:
    """A versão maior de hoje de cada tabela do dicionário (lida uma vez por processo)."""
    from base.dicionario import (
        TABELAS,
    )  # o dicionário é grande: só quando o portão precisa

    return {
        nome: versao_maior(tabela.versao_do_contrato)
        for nome, tabela in TABELAS.items()
    }


def prova_publicavel(texto: str) -> bool:
    """A prova pode ir para o catálogo público: não é vazia e não tem caminho, IP ou e-mail."""
    return bool(texto.strip()) and _FORA_DA_PROVA.search(texto) is None


def _valida(prova: Prova | None, hoje: date) -> bool:
    return prova is not None and bool(prova.prova.strip()) and prova.data <= hoje


def _vencida(prova: Prova, hoje: date) -> bool:
    return hoje - prova.data > PRAZO_DA_PROVA


def _falta_da_tabela(
    registro: Prontidao | None, versao_de_hoje: int | None, hoje: date
) -> Falta | None:
    if registro is None:
        return Falta.SEM_PRONTIDAO
    provas = (registro.cruzada, registro.qualidade, registro.dicionario)
    if not all(_valida(prova, hoje) for prova in provas):
        return Falta.SEM_PRONTIDAO
    cruzada, qualidade = registro.cruzada, registro.qualidade
    assert cruzada is not None and qualidade is not None  # conferido em `_valida`
    if not cruzada.independencia.strip():
        return Falta.SEM_PRONTIDAO
    if versao_de_hoje != registro.versao_maior:
        return Falta.CONTRATO_MUDOU
    if _vencida(cruzada, hoje) or _vencida(qualidade, hoje):
        return Falta.PRONTIDAO_VENCIDA
    return None


def negacao_da_prontidao(
    tabelas: Iterable[str],
    registro: Mapping[str, Prontidao],
    versoes: Mapping[str, int],
    hoje: date,
) -> Falta | None:
    """Por que estas tabelas não podem servir hoje, ou None se **todas** estão prontas (campo
    calculado de duas tabelas exige as duas). Sem tabela nenhuma, nega."""
    tabelas = tuple(tabelas)
    if not tabelas:
        return Falta.SEM_TABELA
    for tabela in tabelas:
        falta = _falta_da_tabela(registro.get(tabela), versoes.get(tabela), hoje)
        if falta is not None:
            return falta
    return None


# --- D11 (ADR 0108, Emenda 2): prontidão de piloto, só para a organização marcada como piloto ---
#
# Separada do registro cheio: a tabela tem a exigência 7 (qualidade automática) em dia e o dicionário **escrito**
# (a 8 sem a leitura do Tiago), e a versão maior do contrato conferida. A 6 (conferência cruzada) fica dispensada,
# e por isso todo bloco servido assim leva o aviso abaixo. Dar piloto a uma tabela é nível 2 da mesa Dados com as
# duas provas; tirar é nível 3. A tabela sai daqui quando ganha a prontidão cheia.

# Texto público (D11.3): a frase de todo bloco servido pelo caminho de piloto. Um lugar só.
AVISO_DE_PILOTO = "Dado de piloto: passou na qualidade automática, mas ainda não na conferência cruzada com outra fonte."


class ProntidaoDePiloto(NamedTuple):
    """As duas provas do piloto (7 e 8 escrita) e a versão maior conferida. Vazio = falta."""

    versao_maior: int
    qualidade: Prova | None  # exigência 7, vence em `PRAZO_DA_PROVA`
    dicionario: Prova | None  # exigência 8 escrita


# As entradas são da mesa Dados (linha 784), só com as duas provas existindo e a marca de pessoa decidida:
# a marca de cada uma está decidida (pela raiz medida em `scripts.conferir_sem_pessoa` ou pela montagem sem pessoa) e o placar de qualidade de 12/11/2026 está verde.
PRONTIDAO_DE_PILOTO: dict[str, ProntidaoDePiloto] = {
    "carteiras_dos_fundos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "fca_geral": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "rotulos_atraso": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "fips_registrados": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "susep_seguros": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "cnpj_situacao_especial": ProntidaoDePiloto(
        versao_maior=2,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "ans_beneficiarios": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 13), "placar-qualidade-2026-11-13"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "cnpj_empresas_pj": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "cnpj_estabelecimentos_pj": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "entradas_de_socio_pj": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "trocas_de_auditor": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "aneel_samp": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "anp_concessionarios": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "eventos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 12), "placar-qualidade-2026-11-12"),
        dicionario=Prova(date(2026, 11, 12), "dicionario-escrito-2026-11-12"),
    ),
    "anvisa_por_empresa": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 13), "placar-qualidade-2026-11-13"),
        dicionario=Prova(date(2026, 11, 13), "dicionario-escrito-2026-11-13"),
    ),
    # a ficha da empresa (linha 841): 23699215 linhas, zero achado no placar, zero raiz fora da lista de PJ
    "cnpj_situacao_cadastral": ProntidaoDePiloto(
        versao_maior=2,
        qualidade=Prova(date(2026, 11, 14), "placar-qualidade-2026-11-14"),
        dicionario=Prova(date(2026, 11, 14), "dicionario-escrito-2026-11-14"),
    ),
    # a rede (linha 784): placar de 16/11/2026 sem vermelho; 95051, 2309558 e 194604 linhas; os dois achados de ligacoes e identificadores têm explicação escrita
    "entidades": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 16), "placar-qualidade-2026-11-16"),
        dicionario=Prova(date(2026, 11, 16), "dicionario-escrito-2026-11-16"),
    ),
    "ligacoes": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 16), "placar-qualidade-2026-11-16"),
        dicionario=Prova(date(2026, 11, 16), "dicionario-escrito-2026-11-16"),
    ),
    "identificadores": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 16), "placar-qualidade-2026-11-16"),
        dicionario=Prova(date(2026, 11, 16), "dicionario-escrito-2026-11-16"),
    ),
    # lote 1 da linha 978: placar de 18/11/2026 sem vermelho (aneel_indicadores_comerciais 280019 linhas, ans_idss 75034,
    # fii_administradores 115, fii_informe_mensal 64213, fip_informe 32919, pgfn_divida 8519520, ifdata_valores 54571412);
    # aneel_inadimplencia e fii_ativos mediram vermelho com a chave do rascunho e entraram no lote 2B
    "aneel_indicadores_comerciais": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "ans_idss": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fii_administradores": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fii_informe_mensal": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fip_informe": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    # lote 2A da linha 978: placar de 18/11/2026 sem vermelho e raiz do CNPJ toda dentro da cnpj_empresas_pj (medido por
    # scripts.conferir_sem_pessoa); as outras 13 tabelas medidas do lote 2 deram vermelho sem explicação e ficaram de fora
    "fre_comites": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fre_distribuicao_capital": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fre_diversidade": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fre_empregados": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fre_remuneracao_extremos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "pareceres_dfp": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "pareceres_itr": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "debentures_assembleias": ProntidaoDePiloto(
        versao_maior=2,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "processos_nas_notas": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    # lote 2B da linha 978: aneel_inadimplencia e fii_ativos (vermelhas no lote 1 só pela chave do rascunho; medidas de
    # contagem na VM em 18/11/2026 acharam a chave certa) e cvm_fiagro (verde no lote 2, 2.934 linhas)
    "aneel_inadimplencia": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "fii_ativos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "cvm_fiagro": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "ifdata_valores": ProntidaoDePiloto(
        versao_maior=2,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    "pgfn_divida": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 18), "placar-qualidade-2026-11-18"),
        dicionario=Prova(date(2026, 11, 18), "dicionario-escrito-2026-11-18"),
    ),
    # linha 981 (ADR 0108, Emenda 3, D11.4): sanções da CGU, embargos do IBAMA e Lista Suja do MTE. Têm marca de pessoa
    # (`pessoa=True`) e só entram porque o servidor guarda apenas a cópia reduzida só-PJ, conferida por `conferir_cadastros`;
    # a porta serve só a linha com `trata_como_pessoa` falso. Placar de 19/11/2026 sem vermelho (36598, 15466 e 133 linhas)
    "sancoes_cgu": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "ibama_embargos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "mte_lista_suja": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    # setores da linha 978: só pela cópia reduzida (`COPIA_REDUZIDA_PELA_RAIZ`); placar de 19/11/2026 sem vermelho (27196 e
    # 6427133 linhas), com o motivo de cada vazio e de cada salto escrito na regra
    "empresa_serie": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "anatel_acessos": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    # fontes ampliadas da linha 978 (ordem C da Diretoria, 19/11/2026): anatel_pados, anatel_produtos_homologados,
    # anp_tancagem e mte_pat. O contrato diz `pessoa=False`, mas parte das linhas é de titular de MEI ou de empresário
    # individual (`trata_como_pessoa`), então só passam pela cópia reduzida só-PJ (`AMPLIADAS`, degrau 8), conferida por
    # `conferir_cadastros`; a porta serve só a linha com `trata_como_pessoa` falso. Placar de 19/11/2026 sem vermelho
    # (89495, 189405, 14679 e 110502 linhas)
    "anatel_pados": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "anatel_produtos_homologados": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "anp_tancagem": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "mte_pat": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    # compras públicas da linha 988: o cadastro de fornecedores do SICAF. O contrato diz `pessoa=False`, mas parte das
    # linhas é de MEI, empresário individual, grupo 4 ou raiz que a Receita guardada não tem (`trata_como_pessoa`), e
    # 5.084 que o próprio SICAF chama de empresário individual estavam sem a marca (conferência de 25/11/2026): só passa
    # pela cópia reduzida só-PJ (`COMPRAS_PUBLICAS`, degrau 9), que tira também essas, conferida por `conferir_cadastros`.
    # O `bps_compras` fica de fora até a queda de linhas de 2022 para 2023 ter a causa conferida (o placar a acusa).
    # O placar do SICAF foi medido no ensaio de 25/11/2026 (contêiner descartável, acervo só leitura, a saída não
    # gravada na VM): a tabela inteira, verde, sem achado
    "comprasgov_sicaf": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 25), "placar-qualidade-ensaio-2026-11-25"),
        dicionario=Prova(date(2026, 11, 25), "dicionario-escrito-2026-11-25"),
    ),
    # lote 3 da linha 978: placar de 19/11/2026 sem vermelho e sem coluna de CNPJ (a marca de pessoa não se aplica);
    # as outras tabelas medidas do lote deram vermelho sem explicação verificada e ficaram de fora
    "anm_amb_agua_mineral": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "antt_siade": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "bcb_selic_focus": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "cftc_cot_agro": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "cnes_competencias": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "comex_cafe": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "comex_urf": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "comex_via": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "conab_cafe": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "faostat_cafe": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "ma_datas": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "ons_capacidade": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
    "usda_psd_cafe": ProntidaoDePiloto(
        versao_maior=1,
        qualidade=Prova(date(2026, 11, 19), "placar-qualidade-2026-11-19"),
        dicionario=Prova(date(2026, 11, 19), "dicionario-escrito-2026-11-19"),
    ),
}

# A marca de pessoa decidida (D11.4), pelas mesmas regras de `tests/test_porta_sem_pessoa.py`: a rede não tem
# marca por linha (a porta a filtra pelas entidades), a montagem de três tabelas já tira a pessoa, e só tabela
# com coluna de CNPJ, raiz ou CPF precisa da marca.
TABELAS_DA_REDE = frozenset({"entidades", "ligacoes", "identificadores"})
# sem pessoa por construção: a montagem nem deixa entrar o empresário individual nem o grupo 4 (linha 584)
# ans_beneficiarios, ifdata_valores e susep_seguros (linha 904, lote 4): o CNPJ só vem da ponte da fonte, e a linha da ponte marcada como pessoa ou fora da fonte deixa o CNPJ vazio (tests/test_cnpj_pela_ponte.py)
# sem pessoa pela raiz (linha 789): as de CNPJ ou raiz (aneel_samp, anp_concessionarios, carteiras_dos_fundos, cnpj_situacao_cadastral, cvm_fiagro (pela raiz separada cnpj_basico), demonstracoes_como_era, eventos, fca_geral, fips_registrados, rotulos_atraso) têm todo CNPJ dentro da cnpj_empresas_pj, medido por scripts.conferir_sem_pessoa antes de cada concessão de piloto; as outras (cnpj_empresas_pj, cnpj_estabelecimentos_pj, entradas_de_socio_pj, participacoes_de_socio_pj) não têm CNPJ de pessoa na montagem
SEM_PESSOA_NA_MONTAGEM = frozenset(
    {
        "controladas_primeiro_fre",  # linha 1045: só a sociedade com CNPJ que confere e não é CPF completado com zeros (`cnpj_de_empresa`), sem nome
        "aneel_samp",
        "anp_concessionarios",
        "ans_beneficiarios",
        "carteiras_dos_fundos",
        "cnpj_empresas_pj",
        "cnpj_estabelecimentos_pj",
        "cnpj_situacao_cadastral",
        "cvm_fiagro",
        "debentures_assembleias",
        "demonstracoes_como_era",
        "emissores",
        "entradas_de_socio_pj",
        "participacoes_de_socio_pj",
        "eventos",
        "fca_geral",
        "fips_registrados",
        "fre_comites",
        "fre_distribuicao_capital",
        "fre_distribuicao_capital_por_classe",
        "fre_diversidade",
        "fre_empregados",
        "fre_remuneracao_extremos",
        "ifdata_valores",
        "ofertas_cnpj_dos_devedores",
        "pareceres_dfp",
        "pareceres_itr",
        "processos_nas_notas",
        "rotulos_atraso",
        "susep_seguros",
    }
)
COLUNA_DE_CNPJ = re.compile(r"cnpj|raiz|cpf", re.IGNORECASE)
# ADR 0108, Emenda 3 (19/11/2026), D11.4: "tabela marcada com pessoa só sai pelo piloto quando o servidor guarda apenas a
# cópia reduzida só-PJ, conferida por máquina (conferir_cadastros), e a resposta serve só a linha com marca de pessoa
# falsa". São as tabelas que `base/recorte_dos_cadastros.py` reduz (só linha de empresa, raiz na `cnpj_empresas_pj`,
# texto livre sem CPF nem e-mail) e que têm a marca por linha (`linhas_de_pessoa`), que a porta usa para esconder o resto.
COPIA_REDUZIDA_SO_PJ = frozenset({"sancoes_cgu", "ibama_embargos", "mte_lista_suja"})
# linha 978 (PR B dos setores): as duas tabelas dos setores com CNPJ ou raiz e sem marca por linha. A tabela inteira, de casa,
# tem raiz fora da `cnpj_empresas_pj` e linha sem documento; ao servidor da API só vai a cópia de
# `base/recorte_dos_setores.py` (raiz dentro da lista sem MEI, linha sem documento fora, sem nome), conferida por máquina a
# cada montagem (`conferir_setores`). Por isso contam como decididas: a negação é da cópia que o servidor guarda.
COPIA_REDUZIDA_PELA_RAIZ = frozenset({"empresa_serie", "anatel_acessos"})


def pessoa_decidida(
    nome: str, *, pessoa: bool, colunas: Iterable[str], linhas_de_pessoa: str
) -> bool:
    """A tabela não guarda pessoa e tem a marca de pessoa decidida (ou não precisa dela)?

    A tabela marcada com pessoa só conta quando é a cópia reduzida só-PJ de `COPIA_REDUZIDA_SO_PJ` **e** tem a marca
    por linha: sem ela a porta não separa a empresa da pessoa e a tabela segue fechada (D11.4, Emenda 3).
    """
    if pessoa and not (nome in COPIA_REDUZIDA_SO_PJ and linhas_de_pessoa.strip()):
        return False
    if (
        nome in TABELAS_DA_REDE
        or nome in SEM_PESSOA_NA_MONTAGEM
        or nome in COPIA_REDUZIDA_PELA_RAIZ
    ):
        return True
    if not any(COLUNA_DE_CNPJ.search(coluna) for coluna in colunas):
        return True
    return bool(linhas_de_pessoa.strip())


@cache
def tabelas_com_pessoa_decidida() -> frozenset[str]:
    """As tabelas do dicionário sem pessoa e com a marca de pessoa decidida: só estas podem sair pelo piloto.

    Fica fora a tabela marcada com pessoa (salvo a cópia reduzida só-PJ do D11.4) e a que tem coluna de CNPJ sem `linhas_de_pessoa` nem ser da rede (o
    inventário `AINDA_SEM_A_MARCA`). `pessoa_tirada_na_rota` não basta: na dúvida, a leitura mais estreita.
    """
    from base.dicionario import TABELAS

    return frozenset(
        nome
        for nome, tabela in TABELAS.items()
        if pessoa_decidida(
            nome,
            pessoa=tabela.pessoa,
            colunas=tabela.colunas,
            linhas_de_pessoa=tabela.linhas_de_pessoa,
        )
    )


def _falta_do_piloto(
    registro: ProntidaoDePiloto | None,
    versao_de_hoje: int | None,
    pessoa_decidida: bool,
    hoje: date,
) -> Falta | None:
    if registro is None or not pessoa_decidida:
        return Falta.SEM_PRONTIDAO
    qualidade, dicionario = registro.qualidade, registro.dicionario
    if not (_valida(qualidade, hoje) and _valida(dicionario, hoje)):
        return Falta.SEM_PRONTIDAO
    assert qualidade is not None  # conferido em `_valida`
    if versao_de_hoje != registro.versao_maior:
        return Falta.CONTRATO_MUDOU
    if _vencida(qualidade, hoje):
        return Falta.PRONTIDAO_VENCIDA
    return None


def negacao_do_piloto(
    tabelas: Iterable[str],
    registro: Mapping[str, ProntidaoDePiloto],
    versoes: Mapping[str, int],
    pessoa_decidida: frozenset[str],
    hoje: date,
) -> Falta | None:
    """Por que estas tabelas não podem servir hoje nem pelo piloto, ou None se **todas** têm o registro de
    piloto em dia e a marca de pessoa decidida. Sem tabela nenhuma, nega."""
    tabelas = tuple(tabelas)
    if not tabelas:
        return Falta.SEM_TABELA
    for tabela in tabelas:
        falta = _falta_do_piloto(
            registro.get(tabela), versoes.get(tabela), tabela in pessoa_decidida, hoje
        )
        if falta is not None:
            return falta
    return None


# Ensaio local (linha 800): no PC, com `TICKERLAB_AMBIENTE=ensaio`, toda tabela do dicionário vale como pronta,
# para a apresentação responder sem o VPS. Qualquer outro valor, inclusive vazio, e "producao", deixa o registro
# de verdade intacto (falha fechada: só o valor exato liga).
VARIAVEL_DO_AMBIENTE = "TICKERLAB_AMBIENTE"
AMBIENTE_DE_ENSAIO = "ensaio"
PROVA_DE_ENSAIO = "ensaio-local"
CABECALHO_DO_ENSAIO = "X-TickerLab-Ensaio"
AVISO_DO_ENSAIO = "ensaio local: dado sem prontidao conferida"


def em_ensaio(ambiente: Mapping[str, str] | None = None) -> bool:
    """O processo roda no ensaio local (`TICKERLAB_AMBIENTE=ensaio`, valor exato)?"""
    texto = (ambiente if ambiente is not None else os.environ).get(
        VARIAVEL_DO_AMBIENTE, ""
    )
    return texto.strip().lower() == AMBIENTE_DE_ENSAIO


# Ensaio do piloto (linha 865): com `TICKERLAB_ENSAIO_DO_PILOTO=1` **e** o ensaio ligado, a prova de ensaio vai para
# o registro de piloto, e não para o cheio, para ensaiar a organização do piloto e o aviso. Fora do ensaio, nada.
VARIAVEL_DO_ENSAIO_DO_PILOTO = "TICKERLAB_ENSAIO_DO_PILOTO"
ENSAIO_DO_PILOTO_LIGADO = "1"


def em_ensaio_do_piloto(ambiente: Mapping[str, str] | None = None) -> bool:
    """O ensaio local ensaia o piloto (`TICKERLAB_ENSAIO_DO_PILOTO=1`, valor exato, só dentro do ensaio)?"""
    ambiente = ambiente if ambiente is not None else os.environ
    texto = ambiente.get(VARIAVEL_DO_ENSAIO_DO_PILOTO, "")
    return em_ensaio(ambiente) and texto.strip() == ENSAIO_DO_PILOTO_LIGADO


def _prova_de_ensaio(hoje: date | None) -> Prova:
    # ontem (UTC): vale em qualquer fuso do Brasil, e a prova de ensaio nunca vence no dia
    dia = hoje or datetime.now(UTC).date() - timedelta(days=1)
    return Prova(dia, PROVA_DE_ENSAIO, PROVA_DE_ENSAIO)


def registro_vigente(
    ambiente: Mapping[str, str] | None = None, hoje: date | None = None
) -> Mapping[str, Prontidao]:
    """O registro que o portão e o catálogo leem: o de verdade, ou, só no ensaio, o de verdade mais uma prova
    de ensaio (datada de ontem) nas tabelas que ainda não têm registro. Fora do ensaio, e no ensaio do piloto,
    devolve `PRONTIDAO` mesmo (o mesmo objeto)."""
    if not em_ensaio(ambiente) or em_ensaio_do_piloto(ambiente):
        return PRONTIDAO
    prova = _prova_de_ensaio(hoje)
    de_ensaio = {
        nome: Prontidao(versao, prova, prova, prova)
        for nome, versao in versoes_maiores().items()
    }
    return {**de_ensaio, **PRONTIDAO}


def registro_de_piloto_vigente(
    ambiente: Mapping[str, str] | None = None, hoje: date | None = None
) -> Mapping[str, ProntidaoDePiloto]:
    """O registro de piloto que o portão lê: o de verdade (o mesmo objeto) ou, só no ensaio do piloto, o de
    verdade mais a prova de ensaio nas tabelas que ainda não o têm. A marca de pessoa vale igual no ensaio."""
    if not em_ensaio_do_piloto(ambiente):
        return PRONTIDAO_DE_PILOTO
    prova = _prova_de_ensaio(hoje)
    de_ensaio = {
        nome: ProntidaoDePiloto(versao, prova, prova)
        for nome, versao in versoes_maiores().items()
    }
    return {**de_ensaio, **PRONTIDAO_DE_PILOTO}
