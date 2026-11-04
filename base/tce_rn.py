"""Leitor do TCE-RN (API de dados abertos): unidades, licitações e participantes por CNPJ (API dados, linha 662).

Uso interno; licença a confirmar (ADR 0102, Emenda 2). Mesmo molde de `base/contratos_tces.py`: só leitura de
bytes já baixados (o download, o ritmo e a pausa ficam no script de carga), linhas simples e **só de pessoa
jurídica** (ADR 0075): documento que não é um CNPJ de 14 caracteres com DV certo é descartado e contado em
`Leitura.descartadas`. A fonte mascara alguns documentos (`xxx635354xx`) e um CPF com zeros à esquerda também
teria 14 dígitos: o DV é o que separa os dois.

**Nunca entram** nomes de participante (o de um MEI é o da pessoa), texto livre (objeto, descrição do lote)
nem o contato da unidade. O nome da unidade (prefeitura, câmara, autarquia) entra: é órgão público.

**Sem olhar o futuro**: a fonte traz a data do ato (`dataPublicacaoLicitacaoPublica`), não a data em que a linha
ficou pública. Toda linha leva `disponivel_em`, a data do download que o chamador informa.

Formatos conferidos em 04/11/2026 (validação da linha 637 e amostra da linha 662):
- **Unidades** (`JurisdicionadosTCE`): lista de 923; só 586 têm `cnpj` (as outras vêm `null`).
- **Licitações** (`LicitacaoPublica/{unidade}/{início}/{fim}`): uma linha por lote, não por licitação;
  `idLoteParticipanteClassificado = 0` é licitação sem lote (sem vencedor a buscar). Valores vêm ora número,
  ora texto com vírgula decimal (`"0,00"`). Datas `dd/mm/aaaa hh:mm:ss`.
- **Participantes** (`ParticipantesDeLicitacao/{lote}`): lista; `ordemClassificacao` 1 é o classificado
  (vencedor), `valorProposta` é texto com vírgula. Lote `0` devolve lista vazia.
"""

import json
from datetime import date

from base.contratos_tces import (
    Leitura,
    Linha,
    _carimbar,
    _cnpj_de_pj,
    _copiar,
    _data_iso,
    _numero,
    _texto,
)

TRIBUNAL = "rn"
SEM_LOTE = 0

CAMPOS_UNIDADE = {
    "identificadorUnidade": "id_unidade",
    "codigoOrgao": "codigo_orgao",
    "nomeOrgao": "nome_unidade",
}
CAMPOS_LICITACAO = {
    "codigoJurisdicionado": "codigo_jurisdicionado",
    "numeroLicitacao": "numero_licitacao",
    "anoLicitacao": "ano_licitacao",
    "procedimentoLicitatorio": "procedimento",
    "modalidade": "modalidade",
    "tipoObjeto": "tipo_objeto",
    "numeroLote": "numero_lote",
    "numeroRecibo": "numero_recibo",
    "situacaoDivulgacaoLicitacaoPublica": "situacao_divulgacao",
    "situacaoProcedimentoLicitacao": "situacao",
    "linkEdital": "link_edital",
}
DATAS_DA_LICITACAO = {
    "dataPublicacaoLicitacaoPublica": "data_publicacao",
    "dataAberturaRecebimento": "data_abertura",
}
VALORES_DA_LICITACAO = {
    "valorTotalOrcado": "valor_orcado",
    "valorReferencia": "valor_referencia",
}


def _corpo_em_lista(corpo: bytes) -> list[dict[str, object]]:
    dados = json.loads(corpo.decode("utf-8-sig"))
    return dados if isinstance(dados, list) else []


def ler_unidades(corpo: bytes, coletado_em: date) -> Leitura:
    """O cadastro de unidades jurisdicionadas. Todas ficam; `cnpj` é None quando a fonte não traz um válido.

    Aqui `descartadas` conta as unidades sem CNPJ válido (ficam na tabela, só sem o documento): a
    ligação com a base é pelo CNPJ, então é bom saber quantas não ligam (586 de 923 em 04/11/2026).
    """
    leitura = Leitura()
    for item in _corpo_em_lista(corpo):
        linha = _copiar(item, CAMPOS_UNIDADE)
        linha["cnpj"] = _cnpj_de_pj(item.get("cnpj"))
        linha["inicio_atividade"] = _data_iso(item.get("dataInicioAtividade"))
        linha["fim_atividade"] = _data_iso(item.get("dataTerminoAtividade"))
        if linha["cnpj"] is None:
            leitura.descartadas += 1
        leitura.linhas.append(_carimbar(linha, TRIBUNAL, "unidades", coletado_em))
    return leitura


def ler_licitacoes(corpo: bytes, id_unidade: int, coletado_em: date) -> Leitura:
    """As licitações de uma unidade num período, uma linha por lote.

    `id_lote` é o `idLoteParticipanteClassificado` (None quando a licitação não tem lote: 0 na fonte); é a
    chave para buscar os participantes. O objeto e a descrição do lote nunca são lidos.
    """
    leitura = Leitura()
    for item in _corpo_em_lista(corpo):
        linha = _copiar(item, CAMPOS_LICITACAO)
        for origem, destino in DATAS_DA_LICITACAO.items():
            linha[destino] = _data_iso((_texto(item.get(origem)) or "").split(" ")[0])
        for origem, destino in VALORES_DA_LICITACAO.items():
            linha[destino] = _numero(item.get(origem))
        linha["id_unidade"] = str(id_unidade)
        linha["id_lote"] = _id_do_lote(item.get("idLoteParticipanteClassificado"))
        leitura.linhas.append(_carimbar(linha, TRIBUNAL, "licitacoes", coletado_em))
    return leitura


def _id_do_lote(valor: object) -> str | None:
    texto = _texto(valor)
    return None if texto is None or texto == str(SEM_LOTE) else texto


def ler_participantes(corpo: bytes, id_lote: str, coletado_em: date) -> Leitura:
    """Todos os participantes de um lote, com a classificação; só os que têm CNPJ válido.

    `ordem_classificacao` 1 é o classificado (o vencedor). O nome e a proposta em texto livre não
    entram; `valor_proposta` vira número.
    """
    leitura = Leitura()
    for item in _corpo_em_lista(corpo):
        documento = _cnpj_de_pj(item.get("documentoParticipante"))
        if documento is None:
            leitura.descartadas += 1
            continue
        linha: Linha = {
            "id_lote": id_lote,
            "cnpj": documento,
            "ordem_classificacao": _texto(item.get("ordemClassificacao")),
            "valor_proposta": _numero(item.get("valorProposta")),
        }
        leitura.linhas.append(_carimbar(linha, TRIBUNAL, "participantes", coletado_em))
    return leitura
