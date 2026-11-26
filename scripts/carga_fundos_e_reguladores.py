"""Carga das tabelas dos lotes 1 e 2 das 300 pelo CNPJ (linha 904): FIP e FII da CVM, indicadores, agentes e
fiscalização da ANEEL, IDSS da ANS, RAPP do IBAMA e contratos do PNCP.

    python -m scripts.carga_fundos_e_reguladores                    (todos os retratos guardados)
    python -m scripts.carga_fundos_e_reguladores --pasta /tmp/base  (outra pasta de saída)
    python -m scripts.carga_fundos_e_reguladores --refazer          (relê mesmo sem retrato novo)

Lê os arquivos que o arquivista já guardou no acervo (não baixa nada) e grava, em
`<TICKERLAB_ACERVO>/base/<tabela>/`, `fip_informe`, `fii_informe_mensal`, `fii_ativos` e
`fii_administradores` (`base/cvm_fip_fii.py`), `aneel_inadimplencia` e `aneel_indicadores_comerciais`
(`base/aneel_indicadores.py`), `ans_idss` (`base/ans_idss.py`) e, do lote 2, `aneel_agentes`,
`aneel_autos_de_infracao` e `aneel_termos_de_notificacao` (`base/aneel_fiscalizacao.py`) e, do lote 3, as cinco
`bcb_*` (`base/bcb_cadastros.py`) e as duas `antt_*` (`base/antt_cadastros.py`) e, da conferência de 14/11,
`receita_regime_tributario`, `mte_pat`, `anm_tah`, `anatel_pados`, `anatel_produtos_homologados` e `anp_tancagem`
(`base/cadastros_conferidos.py`) e, da conferência de 19/11, `comprasgov_sicaf` e `bps_compras`
(`base/cadastros_conferidos_19_11.py`) e, da linha 1074, as seis `ibama_rapp_*` (`base/ibama_rapp.py`) e, da linha 1123,
`anp_revendedores` e `anp_revendedores_produtos` (`base/anp_revendedores.py`). A linha 1 da fila do montador
acrescenta `pncp_contratos` (`base/pncp.py`). Só CNPJ de dígito certo entra; contato,
endereço e nome de pessoa não chegam ao Parquet, e `trata_como_pessoa` marca o MEI e o empresário
individual (ADR 0075). Feita para o servidor de casa (ADR 0031), depois do arquivista; recusa rodar sem
a versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 nenhum arquivo guardado.

Roda: manual no servidor de casa (a 1ª carga e o cron de casa pedem o "pode" da Diretoria); citado em
dicionario.py.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from base import (
    aneel_fiscalizacao,
    aneel_indicadores,
    anp_revendedores,
    ans_idss,
    antt_cadastros,
    bcb_cadastros,
    cadastros_conferidos,
    cadastros_conferidos_19_11,
    cvm_fip_fii,
    ibama_rapp,
    pncp,
)
from src import acervo
from src.banco.conexao import obter_engine
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_fundos_e_reguladores")

MODULOS = (
    cvm_fip_fii,
    aneel_indicadores,
    ans_idss,
    aneel_fiscalizacao,
    bcb_cadastros,
    antt_cadastros,
    cadastros_conferidos,
    cadastros_conferidos_19_11,
    ibama_rapp,
    pncp,
    anp_revendedores,
)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--refazer", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    montados = 0
    with obter_engine().connect() as conexao:
        for modulo in MODULOS:
            resumo = modulo.montar(
                conexao, pasta, datetime.now(UTC), refazer=opcoes.refazer
            )
            for nome, contagem in resumo.items():
                log.info("%s %s: %s", modulo.__name__, nome, contagem)
            montados += len(resumo)
    if not montados:
        log.warning("nenhum arquivo do lote guardado no acervo")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
