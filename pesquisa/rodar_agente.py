"""Roda uma rodada do agente de pesquisa com um modelo grátis da OpenRouter.

    python -I pesquisa/rodar_agente.py "hipótese" [--modelo openrouter/free] [--pasta P]
    python -I pesquisa/rodar_agente.py --listar-modelos

Com `-I` o Python ignora PYTHONPATH e a pasta atual; por isso este arquivo acrescenta a raiz do
repositório ao `sys.path`, como o `iniciar_servidor.py`. A chave vem de `OPENROUTER_API_KEY` ou do
`.env` da raiz. Vários agentes podem rodar ao mesmo tempo: a cota fica num arquivo só
(`--cota`), dividida entre eles.
"""

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADRAO = Path.home() / "TickerLab-Pesquisa"


def _argumentos(argv: list[str]) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(
        description="Agente de pesquisa com modelo grátis da OpenRouter"
    )
    leitor.add_argument("hipotese", nargs="?", help="UMA hipótese por rodada")
    leitor.add_argument("--modelo", default=None, help="padrão: openrouter/free")
    leitor.add_argument(
        "--pasta", type=Path, default=PASTA_PADRAO, help="memória e documentos"
    )
    leitor.add_argument(
        "--cota", type=Path, default=None, help="SQLite da cota, dividido entre agentes"
    )
    leitor.add_argument(
        "--limite-diario",
        type=int,
        default=None,
        help="50 sem créditos; 1000 com US$ 10",
    )
    leitor.add_argument(
        "--passos", type=int, default=None, help="respostas do modelo por rodada"
    )
    leitor.add_argument(
        "--listar-modelos",
        action="store_true",
        help="modelos grátis com ferramentas, agora",
    )
    return leitor.parse_args(argv)


def principal(argv: list[str]) -> int:
    sys.path.insert(0, str(RAIZ))
    import requests

    from base.arquivo.cliente_http import ClienteHttp
    from pesquisa import agente, openrouter, renderizacao
    from pesquisa.pesquisador import Pesquisador

    args = _argumentos(argv)
    if args.listar_modelos:
        catalogo = requests.get(openrouter.URL_DOS_MODELOS, timeout=60).json()
        print("\n".join(openrouter.modelos_gratis_com_ferramentas(catalogo)))
        return 0
    if not args.hipotese:
        print("diga a hipótese da rodada (ou --listar-modelos)", file=sys.stderr)
        return 2
    cota = openrouter.Cota(
        args.cota or args.pasta / "cota-openrouter.sqlite",
        limite_diario=args.limite_diario or openrouter.LIMITE_DIARIO_PADRAO,
    )
    modelo = openrouter.ModeloOpenRouter(
        openrouter.chave_do_ambiente(RAIZ / ".env"),
        args.modelo or openrouter.MODELO_PADRAO,
        cota,
    )
    renderizador = (
        renderizacao.renderizar if renderizacao.crawl4ai_instalado() else None
    )
    pesquisador = Pesquisador(args.pasta, ClienteHttp(), renderizador=renderizador)
    relatorio = agente.rodar_agente(
        args.hipotese,
        pesquisador,
        modelo,
        maximo_de_passos=args.passos or agente.MAXIMO_DE_PASSOS,
    )
    arquivo = agente.escrever_relatorio(relatorio, args.pasta / "relatorios")
    print(
        f"{relatorio.parou_por}: {len(relatorio.confirmados)} confirmado(s), "
        f"{len(relatorio.pendentes)} pendente(s), {relatorio.passos} passo(s)\n{arquivo}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
