"""Coleta e carga das renúncias da Receita para a base: DIRBI (mensal) e ECF (anual), linha 660 da fila.

    python -m scripts.carga_receita_renuncias --baixar <pasta nova e vazia>      (só baixa)
    python -m scripts.carga_receita_renuncias --origem <pasta baixada>           (grava no acervo)
    python -m scripts.carga_receita_renuncias --origem <pasta> --pasta /tmp/base --forcar

`--baixar` pega do compartilhamento público da Receita (o mesmo do cadastro de CNPJ) o DIRBI de 2025 e 2026 e a
ECF, e escreve `modificados.json` com o `Last-Modified` de cada um, que vira o `disponivel_em` (nenhuma das
duas fontes traz a data de entrega por linha). Os arquivos baixados são dados de fora: ficam numa pasta
nova, nunca no repositório, e esta carga os lê com o Python em modo isolado (`python -I`).

`--origem` grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `receita/dirbi/<AAAAMM>.parquet`: o DIRBI de um mês, sem o CNPJ mascarado;
- `receita/ecf_renuncia.parquet`: a ECF, uma linha por CNPJ, SCP e período.

Licença a confirmar, só uso interno (ADR 0102, Emenda 2); nada é perguntado à fonte. Recusa rodar sem a
versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando.
"""

import argparse
import base64
import hashlib
import json
import logging
import re
import sys
import zipfile
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

from base import receita_renuncias as renuncias
from base.parquet import GRAVADO, gravar_com_versoes
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_receita_renuncias")
RAIZ = "https://arquivos.receitafederal.gov.br/"
WEBDAV = RAIZ + "public.php/webdav/Dados/Obrigacoes_Acessorias/"
ENDERECO_PUBLICO = RAIZ + "Dados/Obrigacoes_Acessorias/"
ARQUIVOS_DO_DIRBI = ("renuncia-por-regime-2025.zip", "renuncia-por-regime-2026.zip")
ARQUIVO_DA_ECF = "renuncia-irpj-csll-ecf.csv"
DICIONARIOS = (
    "renuncia-por-regime-dicionario.csv",
    "renuncia-irpj-csll-ecf-dicionario.csv",
)
PASTAS_DA_FONTE = {"DIRBI": ARQUIVOS_DO_DIRBI, "ECF": (ARQUIVO_DA_ECF,)}
MODIFICADOS = "modificados.json"
ORDEM_DO_DIRBI = ["cnpj", "ano", "mes", "codigo_in", "tributo"]
ORDEM_DA_ECF = ["cnpj", "cod_scp", "dt_ini", "dt_fin"]
TEMPO_LIMITE = 900
TAMANHO_DO_PEDACO = 1 << 20


def _sessao_da_receita() -> tuple[str, dict[str, str]]:
    final = rede.get_com_agente(RAIZ, timeout=60).url
    achado = re.search(r"/s/([A-Za-z0-9]+)", final)
    if not achado:
        raise RuntimeError(f"Receita: sem o token do compartilhamento em {final}")
    chave = base64.b64encode(f"{achado.group(1)}:".encode()).decode()
    return achado.group(1), {"Authorization": f"Basic {chave}"}


def baixar(destino: Path) -> dict[str, str]:
    """Baixa os arquivos para uma pasta nova e vazia e devolve o `Last-Modified` (AAAA-MM-DD) de cada um."""
    if destino.exists() and any(destino.iterdir()):
        raise SystemExit(f"{destino} não está vazia: baixe numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    _, cabecalhos = _sessao_da_receita()
    modificados: dict[str, str] = {}
    for pasta, nomes in PASTAS_DA_FONTE.items():
        for nome in (*nomes, *(d for d in DICIONARIOS if _e_da_pasta(d, pasta))):
            with rede.get_com_agente(
                f"{WEBDAV}{pasta}/{nome}",
                headers=cabecalhos,
                stream=True,
                timeout=TEMPO_LIMITE,
            ) as resposta:
                resposta.raise_for_status()
                with open(destino / nome, "wb") as saida:
                    saida.writelines(resposta.iter_content(TAMANHO_DO_PEDACO))
                modificado = parsedate_to_datetime(resposta.headers["Last-Modified"])
                modificados[nome] = modificado.date().isoformat()
            log.info("baixado %s (modificado em %s)", nome, modificados[nome])
    (destino / MODIFICADOS).write_text(
        json.dumps(modificados, indent=1), encoding="utf-8"
    )
    return modificados


def _e_da_pasta(dicionario: str, pasta: str) -> bool:
    return ("regime" in dicionario) == (pasta == "DIRBI")


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        while pedaco := arquivo.read(TAMANHO_DO_PEDACO):
            resumo.update(pedaco)
    return resumo.hexdigest()


def _origem(caminho: Path, pasta_na_fonte: str) -> dict[str, str]:
    return {
        "url": f"{ENDERECO_PUBLICO}{pasta_na_fonte}/{caminho.name}",
        "sha256": _sha256(caminho),
    }


def _modificado_em(origem: Path, nome: str) -> date:
    registro = json.loads((origem / MODIFICADOS).read_text(encoding="utf-8"))
    return date.fromisoformat(registro[nome])


def carregar_dirbi(origem: Path, saida: Path, forcar: bool = False) -> dict[str, str]:
    """Grava um Parquet por mês de cada ZIP do DIRBI; devolve `AAAAMM -> gravado|igual`.

    Cada ZIP é lido inteiro (os meses vêm misturados no arquivo, então não dá para gravar um mês
    antes de ler o resto); o que já está igual no acervo não é regravado."""
    resultado: dict[str, str] = {}
    for nome in ARQUIVOS_DO_DIRBI:
        caminho = origem / nome
        contagem = renuncias.Contagem()
        with zipfile.ZipFile(caminho) as zip_, zip_.open(zip_.namelist()[0]) as fluxo:
            tabela = renuncias.ler_dirbi(fluxo, _modificado_em(origem, nome), contagem)
        log.info("%s: %s", nome, contagem.para_manifesto())
        origens = [_origem(caminho, "DIRBI")]
        for (ano, mes), parte in renuncias.dirbi_por_mes(tabela):
            destino = saida / "receita" / "dirbi" / f"{ano}{mes:02d}"
            resultado[f"{ano}{mes:02d}"] = gravar_com_versoes(
                lambda parte=parte: parte,
                destino,
                origens,
                ORDEM_DO_DIRBI,
                forcar=forcar,
            )
    return resultado


def carregar_ecf(origem: Path, saida: Path, forcar: bool = False) -> str:
    caminho = origem / ARQUIVO_DA_ECF

    def montar() -> pd.DataFrame:
        contagem = renuncias.Contagem()
        with open(caminho, "rb") as fluxo:
            tabela = renuncias.ler_ecf(
                fluxo, _modificado_em(origem, caminho.name), contagem
            )
        log.info("ECF: %s", contagem.para_manifesto())
        return tabela

    return gravar_com_versoes(
        montar,
        saida / "receita" / "ecf_renuncia",
        [_origem(caminho, "ECF")],
        ORDEM_DA_ECF,
        forcar=forcar,
    )


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--baixar", type=Path, default=None)
    argumentos.add_argument("--origem", type=Path, default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.baixar:
        baixar(opcoes.baixar)
        return 0
    if not opcoes.origem:
        argumentos.error("passe --baixar <pasta nova> ou --origem <pasta baixada>")
    faltam = [
        n
        for n in (*ARQUIVOS_DO_DIRBI, ARQUIVO_DA_ECF, MODIFICADOS)
        if not (opcoes.origem / n).exists()
    ]
    if faltam:
        log.error("faltam em %s: %s", opcoes.origem, ", ".join(faltam))
        return 1
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    meses = carregar_dirbi(opcoes.origem, saida, opcoes.forcar)
    ecf = carregar_ecf(opcoes.origem, saida, opcoes.forcar)
    log.info(
        "DIRBI: %d meses (%d gravados); ECF: %s",
        len(meses),
        sum(1 for r in meses.values() if r == GRAVADO),
        ecf,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
