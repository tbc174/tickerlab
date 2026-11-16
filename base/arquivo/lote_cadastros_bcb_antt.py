"""Lote 3 das 300 tabelas pelo CNPJ (linha 904, 13/11/2026): cadastros do Banco Central (Olinda) e da ANTT.

O que o arquivista passa a guardar, sempre como veio (nome de pessoa e contato ficam no acervo, a tabela
de `base/bcb_cadastros.py` e `base/antt_cadastros.py` não os leva):

- **Banco Central (Olinda, ODbL; família `bcb`):** entidades supervisionadas e cooperativas (a posição do
  dia da coleta), correspondentes no País, filiais de administradoras de consórcio e regimes especiais
  (liquidação extrajudicial e afins);
- **ANTT (dados abertos, CC BY; família `antt`):** operadores de transporte multimodal e o seguro de
  responsabilidade civil dos transportadores.

Escolhas (testes em `tests/test_base_arquivo_lote_cadastros_bcb_antt.py`):
- **a posição de uma data:** o serviço `BcBase` pede a `dataBase` e devolve o cadastro como estava naquele
  dia (conferido em 13/11/2026: 2.358 cooperativas em 30/06/2020 e 2.365 em 31/10/2026, com 894 e 750
  autorizadas). O arquivista pede o dia da coleta, então cada coleta é um endereço novo e a tabela vale
  desde o dia do arquivo, nunca antes;
- **o resto do Olinda não tem data:** correspondentes, filiais e regimes são um retrato só, sempre no mesmo
  endereço; o arquivista guarda de novo quando o conteúdo muda;
- **o Olinda responde `value: []` para o que ainda não saiu:** isso é `SemArquivo`, nunca "ok"
  (`lote_bcb.olinda_com_dados`);
- **o seguro da ANTT:** o pacote guarda um CSV por mês desde 2022 (mais de 90 arquivos de 40 a 80 MB, com a
  placa de cada veículo). Só o arquivo atual (`seguro-responsabilidade-civil.csv`, o último que a ANTT
  regravou) vale: os mensais são o mesmo dado em datas antigas. A placa fica no acervo, nunca na tabela;
- **o cadastro dos multimodais** (`operador-transporte-multimodal`) é só o CSV (o JSON e o dicionário em PDF
  repetem ou explicam). O logradouro, o CEP e o e-mail ficam no acervo.
"""

import json
from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte
from base.arquivo.lote_bcb import OLINDA, olinda_com_dados
from base.arquivo.lote_setoriais import _ckan

MENSAL = "mensal"
# o mesmo endereço de `fontes.PORTAL_DA_ANTT` (aquele módulo importa este, então não dá para importá-lo)
PORTAL_DA_ANTT = "https://dados.antt.gov.br"
SUPERVISIONADAS = (
    OLINDA
    + "BcBase/versao/v2/odata/EntidadesSupervisionadas(dataBase=@d)?@d='{dia}'&$format=json"
)
COOPERATIVAS = (
    OLINDA + "BcBase/versao/v2/odata/Cooperativas(dataBase=@d)?@d='{dia}'&$format=json"
)
CORRESPONDENTES = (
    OLINDA + "Informes_Correspondentes/versao/v1/odata/Correspondentes?$format=json"
)
FILIAIS_DE_CONSORCIO = (
    OLINDA
    + "Informes_FiliaisAdministradorasConsorcios/versao/v1/odata/Filiais?$format=json"
)
REGIMES_ESPECIAIS = OLINDA + "regimes_especiais/versao/v1/odata/Regimes?$format=json"
PACOTE_DOS_MULTIMODAIS = "operador-transporte-multimodal"
PACOTE_DO_SEGURO = "seguro-responsabilidade-civil"
ARQUIVO_DO_SEGURO = "/seguro-responsabilidade-civil.csv"
# o `dataBase` do BcBase é `MM-DD-AAAA` (o formato `AAAA-MM-DD` dá 500 sem explicação)
FORMATO_DO_DIA = "%m-%d-%Y"


def _olinda(url: str) -> Alvo:
    return Alvo(url, ".json", olinda_com_dados(url))


def endereco_do_dia(modelo: str, agora: datetime) -> str:
    """O endereço do BcBase com a posição do dia de `agora`."""
    return modelo.format(dia=agora.strftime(FORMATO_DO_DIA))


def _do_dia(modelo: str) -> Descobrir:
    return lambda cliente, agora: [_olinda(endereco_do_dia(modelo, agora))]


def _fixo(url: str) -> Descobrir:
    return lambda cliente, agora: [_olinda(url)]


def descobrir_seguro(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """O CSV atual do pacote do seguro (sem o mês no nome); os mensais antigos ficam de fora."""
    resposta = cliente.ler(
        f"{PORTAL_DA_ANTT}/api/3/action/package_show?id={PACOTE_DO_SEGURO}"
    )
    recursos = json.loads(resposta.conteudo).get("result", {}).get("resources", [])
    urls = [
        r["url"]
        for r in recursos
        if (r.get("url") or "").lower().endswith(ARQUIVO_DO_SEGURO)
        # o endereço vem do dado do portal: só vale o do próprio portal da ANTT (nada de baixar de outro host)
        and r["url"].startswith(PORTAL_DA_ANTT + "/")
    ]
    if not urls:
        raise ErroDeDescoberta(
            f"{PACOTE_DO_SEGURO}: sem o CSV atual ({ARQUIVO_DO_SEGURO}) em {PORTAL_DA_ANTT}"
        )
    return [Alvo(urls[0])]


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família: `bcb-...` e `antt-...`)."""
    return [
        Fonte("bcb-supervisionadas", MENSAL, _do_dia(SUPERVISIONADAS), "json"),
        Fonte("bcb-cooperativas", MENSAL, _do_dia(COOPERATIVAS), "json"),
        Fonte(
            "bcb-correspondentes", MENSAL, _fixo(CORRESPONDENTES), "json", pesada=True
        ),
        Fonte("bcb-filiais-de-consorcio", MENSAL, _fixo(FILIAIS_DE_CONSORCIO), "json"),
        Fonte("bcb-regimes-especiais", MENSAL, _fixo(REGIMES_ESPECIAIS), "json"),
        Fonte(
            "antt-operadores-multimodais",
            MENSAL,
            _ckan(PORTAL_DA_ANTT, PACOTE_DOS_MULTIMODAIS, formatos=("csv",)),
        ),
        Fonte(
            "antt-seguro-de-responsabilidade-civil",
            MENSAL,
            descobrir_seguro,
            pesada=True,
        ),
    ]
