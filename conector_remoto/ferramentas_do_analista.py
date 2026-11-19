"""As ferramentas do analista que só compõem o que a API já devolve (linha 980, onda 1).

Cada uma é um ou mais pedidos à API pelo `ClienteDaApi`, com a chave do analista, e passa pela mesma
tranca de saída das outras (`Pedidos.entregar`: texto limpo, sem pessoa, dentro do teto). Nenhuma abre rota
nem direito novo: o que a chave não vê a API já nega, e a ferramenta some da lista de quem não tem o
conjunto (`CONJUNTOS_DA_FERRAMENTA`, em `ferramentas.py`, onde ficam também os títulos).
"""

from datetime import date

from mcp.server.mcpserver import MCPServer

from conector_remoto.ferramentas import (
    SO_LEITURA,
    TITULOS_DAS_FERRAMENTAS,
    Cnpj,
    ComoEraEm,
    Pedidos,
    cnpj_do_pedido,
)


def _dia(valor: date | None) -> str | None:
    """O dia como a API o pede (AAAA-MM-DD), ou None se não veio."""
    return valor.isoformat() if valor else None


def registrar(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Põe as ferramentas do analista no servidor (chamada por `registrar_ferramentas`)."""
    _registrar_credito(servidor, pedidos)


def _registrar_credito(servidor: MCPServer, pedidos: Pedidos) -> None:
    """Os fatos de crédito da rota `/credit` (conjunto `credit`)."""

    @servidor.tool(
        title=TITULOS_DAS_FERRAMENTAS["credito_da_empresa"],
        annotations=SO_LEITURA,
        structured_output=False,
    )
    async def credito_da_empresa(cnpj: Cnpj, como_era_em: ComoEraEm = None) -> str:
        """Os fatos de crédito de uma empresa pelo CNPJ, como eram no dia: a situação cadastral e a situação
        especial na Receita, os fatos relevantes dos últimos 12 meses entregues à CVM e, para quem cede
        recebíveis a fundo de direitos creditórios (FIDC), os fundos em que cede, a maior participação como
        cedente, a carteira desses fundos e a maior inadimplência deles. Cada fato traz a fonte e o dia em que
        ficou público (`published_at`); fato não observado não aparece, e isso não quer dizer que o evento não
        aconteceu (os `limits` explicam). Serve para ler, antes da reunião, os sinais objetivos de crédito de
        uma empresa.
        Fonte: cadastro CNPJ da Receita Federal; documentos e informes de FIDC entregues à CVM.
        Não traz: rating, insolvência, elegibilidade como cedente ou sacado, nota ou opinião de crédito, o SCR
        individual do Banco Central, pessoa física, contato nem endereço."""
        numeros = cnpj_do_pedido(cnpj)
        return await pedidos.pedir(
            "credito_da_empresa", f"/credit/{numeros}", {"known_at": _dia(como_era_em)}
        )
