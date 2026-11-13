"""Três tabelas por CNPJ do lote 3 da meta das 300 (linha 904): o DIRBI e a ECF da Receita e os estabelecimentos
habilitados à exportação do SIGSIF. Os leitores (`base/receita_renuncias.py`, `base/sigsif.py`) já existiam; aqui
o que eles leem vira tabela da base, **só de pessoa jurídica** (ADR 0075), no molde da `anvisa_por_empresa`.

- **`receita_dirbi`**: o benefício fiscal que cada empresa declarou por mês, regime e tributo; um Parquet por ano.
- **`receita_ecf_renuncia`**: os incentivos de IRPJ e CSLL da ECF, uma linha por CNPJ, SCP e período.
- **`sigsif_habilitados`**: a quem o MAPA habilitou exportar, para que país, em que área e produto. O CNPJ vem do
  número do SIF, pelo cadastro dos registrados (único ou vazio); a linha sem CNPJ não entra.

**Sem pessoa (a prova está nos testes e no resumo da montagem):**
- só entra CNPJ de 14 caracteres com dígito verificador certo; o mascarado e o torto saem e são contados;
- a raiz de empresário individual, de natureza do grupo 4, de MEI ou que a Receita guardada não tem **sai da
  tabela inteira** (não só marcada): `trata_como_pessoa` fica sempre falso e só existe para a porta recusar uma
  linha que um dia vier diferente. Sem a Receita guardada, todas as raízes contam como pessoa e a tabela fica vazia;
- nenhum nome (razão social, nome empresarial, estabelecimento), endereço, telefone ou e-mail é gravado.

**Sem olhar o futuro:** nenhuma das fontes diz quando cada linha foi entregue; `disponivel_em` é o dia em que o
arquivo foi modificado na fonte (o `Last-Modified`), nunca antes. Um arquivo regravado vale desde o dia dele.

Sem Streamlit; pandas só.
"""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd

from base import cnpj as cnpjs

TABELA_DIRBI = "receita_dirbi"
TABELA_ECF = "receita_ecf_renuncia"
TABELA_HABILITADOS = "sigsif_habilitados"

LINHAGEM = ("origem_sha256", "origem_coletada_em", "montado_em", "versao_do_codigo")
COLUNAS_DO_CNPJ = ("cnpj", "cnpj_basico")

COLUNAS_DO_DIRBI = (
    *COLUNAS_DO_CNPJ, "municipio", "uf", "cnae", "ano", "mes", "periodo", "codigo_in", "tributo",
    "valor", "em_verificacao",
)  # fmt: skip
CHAVE_DO_DIRBI = ("cnpj", "ano", "mes", "codigo_in", "tributo")

COLUNAS_DA_ECF = (
    *COLUNAS_DO_CNPJ, "cod_scp", "dt_ini", "dt_fin", "forma_trib", "forma_apur", "qualif_pj",
    "sit_especial", "cnae", "cod_nat", "exercicio",
)  # fmt: skip
CHAVE_DA_ECF = ("cnpj", "cod_scp", "dt_ini", "dt_fin")

COLUNAS_DOS_HABILITADOS = (
    *COLUNAS_DO_CNPJ, "pais", "area", "sif", "uf", "municipio", "produto", "dt_validade",
    "dt_ocorrencia", "dt_suspensao",
)  # fmt: skip
CHAVE_DOS_HABILITADOS = ("pais", "area", "sif", "produto")

# quem pergunta à Receita guardada quais das raízes (números) são de pessoa; sem a Receita, todas
DescobrirPessoas = Callable[[np.ndarray], np.ndarray]


def separar_pessoa_juridica(
    tabela: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """A `tabela` só com as linhas de pessoa jurídica de CNPJ válido, mais `cnpj` com máscara, `cnpj_basico` e
    `trata_como_pessoa` (sempre falso), e a contagem do que saiu. A coluna `cnpj` entra com 14 caracteres sem
    máscara e sai com máscara (como `cmed` e `divida_estadual`). Trabalha sobre os CNPJs distintos: o DIRBI tem milhões de linhas e poucas centenas de milhares de CNPJs."""
    codigos, unicos = pd.factorize(tabela["cnpj"].astype(object))
    unicos = pd.Series(unicos, dtype="string")
    valido = np.array(
        [bool(isinstance(c, str) and cnpjs.dv_confere(c)) for c in unicos], dtype=bool
    )
    basicos = unicos.str[: cnpjs.TAMANHO_DA_RAIZ]
    de_pessoa = np.zeros(len(unicos), dtype=bool)
    if valido.any():
        numeros = cnpjs.raizes_em_numeros(basicos[valido].drop_duplicates())
        pessoas = descobrir(cnpjs.ordenados(numeros))
        de_pessoa[valido] = cnpjs.contem(
            pessoas, cnpjs.raizes_em_numeros(basicos[valido])
        )
    fica = valido & ~de_pessoa
    presente = (
        codigos >= 0
    )  # CNPJ nulo vira -1 no factorize: nunca herda o veredito de outro
    mantida = presente & fica[codigos]
    contagem = {
        "linhas": len(tabela),
        "cnpj_invalido": int((~(presente & valido[codigos])).sum()),
        "pessoa_ou_fora_da_receita": int(
            (presente & (valido & de_pessoa)[codigos]).sum()
        ),
        "linhas_na_tabela": int(mantida.sum()),
        "cnpjs_na_tabela": int(fica.sum()),
    }
    formatados = unicos.map(lambda c: cnpjs.formatar(c) if isinstance(c, str) else None)
    saida = tabela[mantida].reset_index(drop=True)
    escolha = codigos[mantida]
    saida = saida.assign(
        cnpj=formatados.to_numpy(dtype=object)[escolha],
        cnpj_basico=basicos.to_numpy(dtype=object)[escolha],
        trata_como_pessoa=False,
    )
    return saida, contagem


def _sem_categoria(tabela: pd.DataFrame) -> pd.DataFrame:
    """Texto comum no lugar de categoria (o Parquet e a porta leem os dois, mas o hash e o `concat` não)."""
    return tabela.astype(
        {
            c: "object"
            for c in tabela.columns
            if isinstance(tabela[c].dtype, pd.CategoricalDtype)
        }
    )


def com_linhagem(
    tabela: pd.DataFrame,
    disponivel_em: date,
    origem_sha256: str,
    coletado_em: pd.Timestamp,
    montado_em: pd.Timestamp,
    versao_do_codigo: str,
) -> pd.DataFrame:
    """Os carimbos de cada linha: de que arquivo veio, quando foi baixado e montado e com que código."""
    return tabela.assign(
        disponivel_em=disponivel_em,
        origem_sha256=origem_sha256,
        origem_coletada_em=coletado_em.isoformat(),
        montado_em=montado_em.isoformat(),
        versao_do_codigo=versao_do_codigo,
    )


def dirbi_para_a_base(
    lido: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """O DIRBI lido por `receita_renuncias.ler_dirbi`, só de pessoa jurídica e sem o nome empresarial."""
    pj, contagem = separar_pessoa_juridica(lido, descobrir)
    pj = _sem_categoria(pj)
    # a porta lê `aconteceu_em` como data: o número do mês sozinho viraria vazio
    pj["periodo"] = pd.to_datetime(
        {"year": pj["ano"], "month": pj["mes"], "day": 1}
    ).dt.date
    pj["trata_como_pessoa"] = pj["trata_como_pessoa"].astype(bool)
    pronta = pj[[*COLUNAS_DO_DIRBI, "trata_como_pessoa", "disponivel_em"]]
    return pronta.astype({"ano": "int16", "mes": "int16"}), contagem


def ecf_para_a_base(
    lido: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """A ECF lida por `receita_renuncias.ler_ecf`, só de pessoa jurídica e sem a razão social."""
    from base import receita_renuncias as renuncias

    pj, contagem = separar_pessoa_juridica(lido, descobrir)
    colunas = [
        *COLUNAS_DA_ECF[:-1],
        *renuncias.COLUNAS_DE_BENEFICIO_DA_ECF,
        "exercicio",
        "trata_como_pessoa",
        "disponivel_em",
    ]
    pronta = pj[colunas].assign(
        dt_ini=pd.to_datetime(pj["dt_ini"]).dt.date,
        dt_fin=pd.to_datetime(pj["dt_fin"]).dt.date,
    )
    return pronta, contagem


def habilitados_para_a_base(
    lido: pd.DataFrame, descobrir: DescobrirPessoas
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os habilitados lidos por `sigsif.ler_habilitados`: só os que acharam um CNPJ pelo SIF, de pessoa jurídica
    e sem o nome do estabelecimento. A contagem diz também quantas ficaram sem CNPJ."""
    com_cnpj = lido["cnpj"].notna()
    pj, contagem = separar_pessoa_juridica(lido[com_cnpj], descobrir)
    contagem["linhas"] = len(lido)
    contagem["sem_cnpj_pelo_sif"] = int((~com_cnpj).sum())
    datas = ["dt_validade", "dt_ocorrencia", "dt_suspensao"]
    pronta = pj[
        [*COLUNAS_DOS_HABILITADOS, "trata_como_pessoa", "disponivel_em"]
    ].assign(**{c: pd.to_datetime(pj[c]).dt.date for c in [*datas, "disponivel_em"]})
    return pronta, contagem
