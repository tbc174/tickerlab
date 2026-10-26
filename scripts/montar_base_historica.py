"""Monta a base histórica da CVM (série B1) a partir dos originais do acervo (`base/historico.py`).

    python -m scripts.montar_base_historica                       (todas as tabelas)
    python -m scripts.montar_base_historica eventos negociacoes   (só estas)
    python -m scripts.montar_base_historica cnpj_situacao_especial (retratos do CNPJ, B2)
    python -m scripts.montar_base_historica cnpj_situacao_cadastral (situação cadastral mês a mês, B-30c)
    python -m scripts.montar_base_historica auditores trocas_de_auditor (B3; as trocas leem os auditores)
    python -m scripts.montar_base_historica pareceres_dfp pareceres_itr (T2; parecer do auditor dos CSVs do DFP e do ITR)
    python -m scripts.montar_base_historica securitizacao_certificados securitizacao_cedente_devedor (B-16; informe mensal de CRI, CRA e OTS)
    python -m scripts.montar_base_historica curva_juros            (curva própria do Tesouro, B12)
    python -m scripts.montar_base_historica controladas empresa_serie (B13; a ligação lê as controladas)
    python -m scripts.montar_base_historica notas_dfp              (texto das notas da DFP, do ENET; linha 135)
    python -m scripts.montar_base_historica rotulos_atraso         (rótulo do modelo 8, de DFP, ITR e cadastro)
    python -m scripts.montar_base_historica --pasta /tmp/base     (outra pasta de saída)

Saída padrão: `<TICKERLAB_ACERVO>/base/<tabela>/<ano>.parquet`. Roda no servidor de casa (ADR 0031),
depois que o arquivista guardou os arquivos `cvm-hist-*`. Saída 0 tudo certo; 1 algum original não
abriu (as outras tabelas e anos continuam).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from base import (
    auditores,
    curva,
    empresa_serie,
    enet_notas,
    historico,
    rotulos,
    situacao_cadastral,
)
from base.modelos.atraso import rotulo as rotulo_de_atraso
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("montar_base_historica")

# retratos mensais da "situação especial" do CNPJ (B2, parte 2): não são arquivos anuais
CNPJ = "cnpj_situacao_especial"
# situação cadastral do CNPJ mês a mês (B-30c): os mesmos retratos, outra tabela
CNPJ_CADASTRAL = situacao_cadastral.TABELA
# trocas de auditor (B3): saem de todos os anos de `auditores`, por isso vêm depois deles
TROCAS = "trocas_de_auditor"
# curva de juros própria (B12): sai do CSV do Tesouro Direto, não dos arquivos anuais da CVM
CURVA = curva.TABELA
# empresa ↔ série da prévia do balanço (B13): sai das controladas de todos os anos, por isso vem depois
EMPRESA_SERIE = empresa_serie.TABELA
# rótulo do modelo de atraso (modelo 8): lê o índice de todos os anos da DFP e do ITR e o cadastro
ATRASO = rotulo_de_atraso.TABELA
# texto das notas da DFP (linha 135): vem do ENET (`scripts/carga_enet_notas.py`), não dos arquivos anuais
NOTAS = enet_notas.TABELA
TODAS = [
    *historico.TABELAS,
    CNPJ,
    CNPJ_CADASTRAL,
    TROCAS,
    CURVA,
    EMPRESA_SERIE,
    ATRASO,
    NOTAS,
]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("tabelas", nargs="*", choices=[*TODAS, []], default=[])
    argumentos.add_argument("--pasta", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    # como as outras cargas da base: sem saber o commit, nada é montado (exigência 13, ADR 0055)
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    agora = datetime.now(UTC)
    falhou = False
    with obter_engine().connect() as conexao:
        for nome in opcoes.tabelas or TODAS:
            if nome == CNPJ:
                meses = rotulos.montar_situacao_especial(conexao, pasta, agora)
                log.info("%s: %s", CNPJ, meses or "nenhum mês do CNPJ guardado")
                continue
            if nome == CNPJ_CADASTRAL:
                meses = situacao_cadastral.montar(conexao, pasta, agora)
                log.info(
                    "%s: %s", CNPJ_CADASTRAL, meses or "nenhum mês do CNPJ guardado"
                )
                continue
            if nome == EMPRESA_SERIE:
                ligadas = empresa_serie.montar(conexao, pasta, agora)
                log.info("%s: %d ligações a companhias", EMPRESA_SERIE, ligadas)
                continue
            if nome == CURVA:
                anos = curva.montar(conexao, pasta, agora)
                log.info("%s: %d anos", CURVA, len(anos))
                continue
            if nome == NOTAS:
                try:
                    por_ano = enet_notas.montar(conexao, pasta, agora)
                except enet_notas.SemOIndice as erro:
                    log.error("%s", erro)
                    falhou = True
                    continue
                log.info(
                    "%s: %d anos (%s)",
                    NOTAS,
                    len(por_ano),
                    por_ano or "nenhum texto guardado",
                )
                continue
            if nome == ATRASO:
                linhas = rotulo_de_atraso.montar(conexao, pasta, agora)
                log.info("%s: %d exemplos", ATRASO, linhas)
                continue
            if nome == TROCAS:
                log.info("%s: %d trocas", TROCAS, auditores.montar_trocas(pasta, agora))
                continue
            try:
                linhas = historico.montar(nome, conexao, pasta, agora)
            except historico.ArquivoIlegivel as erro:
                log.error("%s", erro)
                falhou = True
                continue
            anos = ", ".join(f"{ano}: {n}" for ano, n in sorted(linhas.items()))
            log.info(
                "%s: %d anos (%s)",
                nome,
                len(linhas),
                anos or "nenhum original guardado",
            )
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
