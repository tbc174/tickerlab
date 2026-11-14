"""Lista das raízes de CNPJ que são empresa, para as cargas tirarem a pessoa (linhas 916 e 784).

Empresário individual e MEI são pessoa. A `cnpj_empresas_pj` tira o empresário individual pela natureza
jurídica, mas o MEI com natureza de empresa só sai na `cnpj_estabelecimentos_pj` (opção pelo Simples). Por
isso a lista é a **interseção das duas**, como no recorte da API (`montar_recorte_da_api.tirar_raizes_de_mei`).

Leve em memória: as duas tabelas dividem os arquivos pelos 2 primeiros caracteres da raiz, então a
interseção sai arquivo a arquivo, e a lista fica num vetor do Arrow (não em um `set` de textos do Python,
que passava de 7 GB com ~55 milhões de raízes). Só conta; nunca devolve nem imprime uma raiz.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

TABELA_PJ = "cnpj_empresas_pj"
TABELA_ESTABELECIMENTOS = "cnpj_estabelecimentos_pj"
ARQUIVO_VERSIONADO = re.compile(r"\.v\d+\.parquet$")
COLUNA_DA_RAIZ = "cnpj_basico"


@dataclass(frozen=True)
class RaizesDeEmpresa:
    """As raízes que são empresa e a impressão digital dos arquivos de onde saíram."""

    valores: pa.Array
    impressao: str

    @classmethod
    def de_lista(
        cls, raizes: "list[str] | set[str] | frozenset[str]"
    ) -> "RaizesDeEmpresa":
        """Para teste e uso pequeno: a lista vem pronta, a impressão é a dela."""
        ordenadas = sorted(raizes)
        return cls(
            pa.array(ordenadas, type=pa.string()),
            hashlib.sha256("\n".join(ordenadas).encode()).hexdigest(),
        )

    def esta_na_lista(self, raizes: pa.Array | pa.ChunkedArray) -> pa.Array:
        """Vetor de verdadeiro/falso: a raiz (oito dígitos) está na lista de empresas."""
        return pc.is_in(raizes, value_set=self.valores)


def _arquivos_atuais(base: Path, tabela: str) -> dict[str, Path]:
    """Os arquivos atuais (sem as versões `.vN`) de uma tabela da base, pelo nome; sem arquivo, recusa."""
    pasta = base / tabela
    arquivos = {
        a.name: a
        for a in sorted(pasta.glob("*.parquet"))
        if not ARQUIVO_VERSIONADO.search(a.name)
    }
    if not arquivos:
        raise FileNotFoundError(
            f"sem a {tabela} em {pasta}: não dá para conferir quem é pessoa"
        )
    return arquivos


def _raizes_do_arquivo(arquivo: Path) -> pa.Array:
    coluna = pq.read_table(arquivo, columns=[COLUNA_DA_RAIZ]).column(COLUNA_DA_RAIZ)
    return pc.unique(coluna.cast(pa.string()))


def _impressao(*grupos: dict[str, Path]) -> str:
    """SHA-256 dos arquivos atuais das duas tabelas: lista nova (arquivo mudou) refaz a tabela."""
    resumo = hashlib.sha256()
    for grupo in grupos:
        for nome, arquivo in grupo.items():
            resumo.update(nome.encode())
            with arquivo.open("rb") as aberto:
                while bloco := aberto.read(1 << 20):
                    resumo.update(bloco)
    return resumo.hexdigest()


def raizes_de_empresa(base: Path) -> RaizesDeEmpresa:
    """Interseção, arquivo a arquivo, das raízes da `cnpj_empresas_pj` e da `cnpj_estabelecimentos_pj`."""
    empresas = _arquivos_atuais(base, TABELA_PJ)
    estabelecimentos = _arquivos_atuais(base, TABELA_ESTABELECIMENTOS)
    partes: list[pa.Array] = []
    for nome, arquivo in empresas.items():
        outro = estabelecimentos.get(nome)
        if outro is None:
            continue
        das_empresas = _raizes_do_arquivo(arquivo)
        das_estabelecimentos = _raizes_do_arquivo(outro)
        partes.append(
            das_empresas.filter(pc.is_in(das_empresas, value_set=das_estabelecimentos))
        )
    valores = (
        pa.concat_arrays(partes).cast(pa.string())
        if partes
        else pa.array([], type=pa.string())
    )
    return RaizesDeEmpresa(valores, _impressao(empresas, estabelecimentos))
