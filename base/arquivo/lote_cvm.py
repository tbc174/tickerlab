"""Lote CVM do arquivista: mais conjuntos do portal de dados abertos (23/10/2026, linha 200 da fila).

Fundos 555 (informe diário, lâmina, perfil mensal, balancete, extrato, complementares, eventuais e
entrega de documentos), FII (informe mensal, trimestral, anual e demonstrações), securitizadoras
(informe mensal das OTS), FIP, fundos estruturados (`fie-*`), administradores de FII e a arrecadação
da CVM. Cada fonte é um `Fonte` do arquivista que guarda os arquivos do pacote como a CVM os publica
(licença ODbL, já marcada em `src/banco/coletas.py`). O portal não pede chave.

Escolhas (testes em `tests/test_base_arquivo_lote_cvm.py`):
- **LGPD (ADR 0088): nada de cadastro com pessoa.** Os pacotes abaixo foram abertos em 23/10/2026 e só
  trazem CNPJ, fundos e números. Ficaram de fora, por trazer nome ou CPF de pessoa física no próprio
  arquivo: `invnr-cad` (representantes de não residentes, com arquivo só de pessoas), `adm_cart-cad`
  (administradores de carteira, com diretores e sócios), `crowdfunding-cad` (sócios e responsáveis),
  `fi-cad` (gestor com CPF e diretor responsável), `emissor_cepac-cad` e `cia_incent-cad` (diretor e
  responsável), `ato_declr-intermed` (coluna CNPJ_CPF), além de `agente_auton-cad` e
  `consultor_vlmob-cad` (todos pessoas). Entram depois com filtro que tire a pessoa antes de guardar
  (linha da fila);
- **fora também:** `distrpubl` e `emissores` (o portal aponta para a página do gov.br, não para o arquivo);
- **ritmo pelo calendário do pacote:** o informe diário e o que a CVM regrava toda semana rodam
  `semanal`; os documentos mensais rodam `mensal`. As grandes (informe diário, balancete, entrega) são
  `pesada`: o Arquivista as baixa no servidor, nunca no PC;
- **o pacote que a CVM trocar de nome ou esvaziar** falha na descoberta com o nome dele (um pacote
  sem arquivo é erro, nunca "ok").

Este módulo não importa `fontes.py` (que importa este): usa a descoberta de `lote_brasil2`.
"""

from datetime import datetime

from base.arquivo.coleta import Alvo, Cliente, Descobrir, Fonte
from base.arquivo.lote_brasil2 import descobrir_ckan

PORTAL_DA_CVM = "https://dados.cvm.gov.br"

SEMANAL = "semanal"
MENSAL = "mensal"

# id da fonte -> (ritmo, pesada, pacotes do portal)
PACOTES: dict[str, tuple[str, bool, tuple[str, ...]]] = {
    # fundos 555
    "cvm-fundos-informe-diario": (SEMANAL, True, ("fi-doc-inf_diario",)),
    "cvm-fundos-lamina": (MENSAL, False, ("fi-doc-lamina",)),
    "cvm-fundos-perfil-mensal": (MENSAL, False, ("fi-doc-perfil_mensal",)),
    "cvm-fundos-balancete": (MENSAL, True, ("fi-doc-balancete",)),
    "cvm-fundos-extrato": (MENSAL, False, ("fi-doc-extrato",)),
    "cvm-fundos-complementares": (MENSAL, False, ("fi-doc-compl",)),
    "cvm-fundos-eventuais": (SEMANAL, False, ("fi-doc-eventual",)),
    "cvm-fundos-entrega": (MENSAL, True, ("fi-doc-entrega",)),
    # fundos imobiliários
    "cvm-fii-mensal": (MENSAL, False, ("fii-doc-inf_mensal",)),
    "cvm-fii-trimestral": (MENSAL, False, ("fii-doc-inf_trimestral",)),
    "cvm-fii-anual": (MENSAL, False, ("fii-doc-inf_anual",)),
    "cvm-fii-demonstracoes": (MENSAL, False, ("fii-doc-dfin",)),
    "cvm-fii-administradores": (SEMANAL, False, ("adm_fii-cad",)),
    # securitizadoras e participações
    "cvm-securitizadoras-ots": (SEMANAL, False, ("securit-doc-inf_mensal_ots",)),
    "cvm-fip-trimestral": (MENSAL, False, ("fip-doc-inf_trimestral",)),
    "cvm-fip-quadrimestral": (MENSAL, False, ("fip-doc-inf_quadrimestral",)),
    # fundos estruturados e arrecadação
    "cvm-fie-balancete": (MENSAL, False, ("fie-doc-balancete",)),
    "cvm-fie-balanco": (MENSAL, False, ("fie-doc-balanco",)),
    "cvm-fie-medidas": (SEMANAL, False, ("fie-medidas",)),
    "cvm-arrecadacao": (MENSAL, False, ("arrecadacao-receita-publica",)),
}


def _do_portal(*pacotes: str) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return descobrir_ckan(cliente, PORTAL_DA_CVM, *pacotes)

    return descobrir


def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    return [
        Fonte(id_, ritmo, _do_portal(*pacotes), pesada=pesada)
        for id_, (ritmo, pesada, pacotes) in PACOTES.items()
    ]
