"""Carga noturna das versões antigas de DFP e ITR do ENET (série 1 da base de ML, PR 7).

    python -m scripts.carga_enet                          (2010 até o ano atual, até as 6h)
    python -m scripts.carga_enet --desde 2020 --parar-as 05:30

Roda no servidor de casa, de madrugada (ADR 0031). Para cada arquivo anual da CVM, do DFP mais novo
para o mais velho e depois o ITR, lê o índice e baixa do ENET as versões que não são a mais nova (a
mais nova vem dos dados abertos), um pacote por vez (`base/enet_coleta.py`). Guarda o XML limpo no
acervo e no registro de coletas.

- **Janela:** não começa um pacote depois de `--parar-as` (6h): a noite seguinte retoma de onde
  parou, porque o que já está guardado é pulado.
- **Falha passageira** (pacote cortado, a CVM devolvendo outra coisa) fica para a noite seguinte e
  não derruba a tarefa. A tarefa devolve 1 (o Kuma avisa) só se nada veio e algo falhou pela
  primeira vez. A mensagem diz de que tipo: pacote em formato que o leitor não conhece
  (`FormatoNaoLido`) ou falha de rede/pacote cortado (aí sim, a fonte pode estar fora do ar).
- **Pacote que não se lê** fica registrado e é deixado de lado por um mês (sem leitor: na hora;
  cortado: depois de 3 noites; `base.enet_coleta.deixados_de_lado`). Quando ele volta a falhar, não
  é novidade e não acende o Kuma. Depois de ensinar o leitor um formato novo: `--tentar-de-novo`.
  Falha de rede acende sempre e nunca deixa um pacote de lado.
- Os pacotes do formato antigo (`.dfp` até ~2020) são lidos por `base/enet_antigo.py`.
- Depois da carga inicial, a tarefa continua útil: as empresas reapresentam documentos o tempo
  todo, e cada reapresentação nova torna antiga a versão de antes.

Roda: cron de casa (todo dia às 0h30); outro script (carga_enet_notas.py).
"""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base.contas_cvm import ler_indice
from base.enet_antigo import FormatoNaoLido
from base.enet_coleta import (
    Baixador,
    ResultadoDaFila,
    baixar_em_fila,
    deixados_de_lado,
    falha_de_rede,
    guardar,
    ja_falharam,
    ja_guardados,
    registrar_falha,
)
from base.ponto_no_tempo import versoes_antigas
from src import demonstracoes as dm
from src import rede
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.carga_enet")
FUSO = ZoneInfo("America/Sao_Paulo")
PRIMEIRO_ANO = 2010  # os dados abertos de DFP começam em 2010 (ITR em 2011)
PARAR_AS = "06:00"
NAO_ENCONTRADO = 404
URLS = {"DFP": dm.URL_DO_DFP, "ITR": dm.URL_DO_ITR}


def _baixar_da_fonte(url: str) -> bytes | None:
    """O arquivo anual da CVM, ou None se ele não existe (404)."""
    resposta = rede.obter(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro("cvm-dfp-itr", _baixar_da_fonte)


def agora() -> datetime:
    return datetime.now(FUSO)


def fim_da_janela(momento: datetime, parar_as: str) -> datetime:
    """O próximo `parar_as` depois de `momento` (às 0h30 → 6h do mesmo dia; às 23h → do seguinte)."""
    hora, minuto = (int(parte) for parte in parar_as.split(":"))
    fim = datetime.combine(momento.date(), time(hora, minuto), tzinfo=momento.tzinfo)
    return fim if momento < fim else fim + timedelta(days=1)


def _indice(motor: sa.Engine, documento: str, ano: int) -> pd.DataFrame | None:
    url = URLS[documento].format(ano=ano)
    with motor.connect() as conexao:
        conteudo = original_mais_recente(conexao, url)
    conteudo = conteudo if conteudo is not None else baixar(url)
    return None if conteudo is None else ler_indice(conteudo, documento)


@dataclass
class ResumoDaCarga:
    baixadas: int = 0
    falhas_de_formato: int = 0  # o leitor não conhece o pacote
    falhas_de_rede: int = 0  # rede, pacote cortado ou outra falha passageira
    falhas_conhecidas: int = 0  # pacote que já tinha falhado antes: não é novidade
    deixados_de_lado: int = 0  # pulados nesta noite por não se lerem (voltam em um mês)

    @property
    def falhas(self) -> int:
        """As falhas que são novidade (as conhecidas não acendem o Kuma de novo)."""
        return self.falhas_de_formato + self.falhas_de_rede


@dataclass
class _Noite:
    """O que vale para a noite inteira: a janela, o baixador e o que já se sabe dos pacotes ruins."""

    motor: sa.Engine
    fim: datetime
    ja_falharam: set[str]  # pacotes que falharam em noites anteriores
    deixados_de_lado: set[str]  # desses, os que nem se baixa nesta noite
    baixador: Baixador
    resumo: ResumoDaCarga = field(default_factory=ResumoDaCarga)

    def ao_falhar(self, link: str, erro: Exception) -> None:
        """Conta a falha pelo tipo e registra a do pacote (a de rede passa sozinha)."""
        if falha_de_rede(erro):
            self.resumo.falhas_de_rede += 1
            return
        with self.motor.begin() as conexao:
            registrar_falha(conexao, link, erro, agora().astimezone(UTC))
        if link in self.ja_falharam:
            self.resumo.falhas_conhecidas += 1
        elif isinstance(erro, FormatoNaoLido):
            self.resumo.falhas_de_formato += 1
        else:
            self.resumo.falhas_de_rede += 1


def _carregar_arquivo(
    noite: _Noite, documento: str, ano: int
) -> ResultadoDaFila | None:
    indice = _indice(noite.motor, documento, ano)
    if indice is None:
        log.info("%s %s não existe na CVM: pulado", documento, ano)
        return None
    with noite.motor.connect() as conexao:
        feitos = ja_guardados(conexao)
    links = versoes_antigas(indice)["link"]
    deixados = noite.deixados_de_lado.intersection(links) - feitos
    noite.resumo.deixados_de_lado += len(deixados)

    def ao_baixar(link: str, pacote: bytes) -> None:
        with noite.motor.begin() as conexao:
            guardar(conexao, link, pacote, datetime.now(UTC))

    resultado = baixar_em_fila(
        links,
        noite.baixador.baixar,
        feitos | deixados,
        ao_baixar,
        continuar=lambda: agora() < noite.fim,
        ao_falhar=noite.ao_falhar,
    )
    log.info(
        "%s %s: %s baixadas, %s já estavam, %s deixadas de lado, %s falharam",
        documento, ano, len(resultado.baixados), resultado.pulados - len(deixados),
        len(deixados), len(resultado.falhas),
    )  # fmt: skip
    return resultado


def carregar(
    motor: sa.Engine,
    desde: int,
    ate: int,
    parar_as: str,
    tentar_de_novo: bool = False,
) -> ResumoDaCarga:
    """Baixa o que falta, DFP do ano mais novo ao mais velho e depois ITR.

    `tentar_de_novo` baixa também os pacotes deixados de lado (depois de ensinar o leitor).
    """
    inicio = agora()
    with motor.connect() as conexao:
        falharam = ja_falharam(conexao)
        deixados = set() if tentar_de_novo else deixados_de_lado(conexao, inicio)
    noite = _Noite(
        motor, fim_da_janela(inicio, parar_as), falharam, deixados, Baixador()
    )
    resumo = noite.resumo
    for documento in URLS:
        for ano in range(ate, desde - 1, -1):
            resultado = _carregar_arquivo(noite, documento, ano)
            if resultado is None:
                continue
            resumo.baixadas += len(resultado.baixados)
            if resultado.interrompida:
                log.info(
                    "Janela acabou (%s): %s baixadas nesta noite",
                    parar_as,
                    resumo.baixadas,
                )
                return resumo
    log.info(
        "Carga em dia: %s baixadas nesta noite; %s deixadas de lado por não se lerem "
        "(--tentar-de-novo depois de ensinar o leitor); %s já conhecidas falharam de novo",
        resumo.baixadas,
        resumo.deixados_de_lado,
        resumo.falhas_conhecidas,
    )
    return resumo


def _avisar_que_nada_veio(resumo: ResumoDaCarga) -> None:
    """Diz de que tipo foram as falhas: 'fora do ar' só vale para falha de rede."""
    if resumo.falhas_de_formato:
        log.error(
            "Nada veio: %s pacotes em formato que o leitor não conhece (veja os avisos acima)",
            resumo.falhas_de_formato,
        )
    if resumo.falhas_de_rede:
        log.error(
            "Nada veio: %s pacotes falharam por rede ou pacote cortado: a fonte pode estar fora do ar",
            resumo.falhas_de_rede,
        )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, help="o ano mais novo (padrão: o atual)")
    argumentos.add_argument(
        "--parar-as", default=PARAR_AS, help="hora de não começar mais"
    )
    argumentos.add_argument(
        "--tentar-de-novo",
        action="store_true",
        help="baixa também os pacotes deixados de lado por não se lerem",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        resumo = carregar(
            motor,
            opcoes.desde,
            opcoes.ate or agora().year,
            opcoes.parar_as,
            opcoes.tentar_de_novo,
        )
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Carga interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    if resumo.falhas and not resumo.baixadas:
        _avisar_que_nada_veio(resumo)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
