"""Uma tabela da base em Parquet com manifesto (série 3 da base de ML, PR 3; ADR 0027, exigência 9;
ADR 0055, exigência 13).

Para as fontes novas que não são "por ano de balanço" (código da ação, emissores, cadastros): grava
`<nome>.parquet` sem ficar pela metade e, ao lado, `<nome>.json` com as linhas, o SHA-256 do
conteúdo (independente da ordem das linhas), a ordem usada no hash, as origens (endereço e SHA-256 de
cada original) e a versão do código que gravou. `conferir_tabela` diz se o Parquet ainda é o anotado.
"""

import hashlib
import io
import json
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pandas as pd

from src.versao_do_codigo import versao_do_codigo

log = logging.getLogger(__name__)
ALGARISMOS_SIGNIFICATIVOS = "%.17g"  # o mesmo número sempre vira o mesmo texto
LINHAS_POR_PEDACO = (
    200_000  # o texto do hash sai em pedaços: a tabela inteira não cabe na memória
)


def gravar_atomico(destino: Path, gravar: Callable[[Path], object]) -> None:
    """Grava num arquivo ao lado e troca de nome no fim: quem lê nunca vê o arquivo pela metade."""
    temporario = destino.with_name(destino.name + ".parcial")
    gravar(temporario)
    os.replace(temporario, destino)


def hash_da_tabela(tabela: pd.DataFrame, ordem: list[str]) -> str:
    """SHA-256 do conteúdo, sem depender da ordem das linhas: ordena por `ordem` e por todas as colunas."""
    canonica = tabela.sort_values(
        [*ordem, *[c for c in tabela.columns if c not in ordem]],
        na_position="first",
        kind="stable",
    ).reset_index(drop=True)
    soma = hashlib.sha256()
    for inicio in range(0, max(len(canonica), 1), LINHAS_POR_PEDACO):
        pedaco = canonica.iloc[inicio : inicio + LINHAS_POR_PEDACO].to_csv(
            index=False,
            header=inicio == 0,
            float_format=ALGARISMOS_SIGNIFICATIVOS,
            date_format="%Y-%m-%d",
        )
        soma.update(pedaco.encode("utf-8"))
    return soma.hexdigest()


def como_no_disco(tabela: pd.DataFrame) -> pd.DataFrame:
    """A tabela como volta do Parquet. O hash é sempre deste jeito: uma coluna `object` com float do
    Python (`1.0`) volta como float64 (`1`), e o hash feito na memória não conferia com o arquivo."""
    memoria = io.BytesIO()
    tabela.to_parquet(memoria, index=False)
    memoria.seek(0)
    return pd.read_parquet(memoria)


def _conferencia_do_contrato(tabela: pd.DataFrame, destino: Path) -> dict[str, object]:
    """A conferência dos valores contra o contrato (`base/conferencia.py`), se a pasta de `destino` é
    de uma tabela do dicionário. Só aviso: um problema, ou a própria conferência falhar, fica anotado
    no manifesto e a montagem segue (bloquear pede o "pode" do Tiago)."""
    nome = None
    try:
        # importado aqui: o dicionário puxa o catálogo de coletas, e quem só grava Parquet não precisa
        from base.conferencia import conferir, tabela_do_destino

        nome = tabela_do_destino(destino.with_suffix(".parquet"))
        if nome is None:
            return {}
        resultado = conferir(tabela, nome).para_manifesto()
    except (
        Exception
    ) as erro:  # aviso: a montagem não pode parar por causa da conferência
        log.exception("conferência do contrato de %s falhou", destino)
        resultado = {
            "tabela": nome,
            "aprovada": False,
            "erro": f"{type(erro).__name__}: {erro}",
        }
    if not resultado["aprovada"]:
        log.warning(
            "%s fora do contrato: %s",
            destino,
            resultado.get("problemas") or resultado.get("erro"),
        )
    return {"conferencia_do_contrato": resultado}


def gravar_tabela(
    tabela: pd.DataFrame,
    destino: Path,
    origens: list[dict[str, str]],
    ordem: list[str],
    *,
    extras: Mapping[str, object] | None = None,
) -> Path:
    """Grava `<destino>.parquet` e o manifesto `<destino>.json`; devolve o caminho do Parquet.

    `extras`: campos a mais no manifesto (ex.: o que ficou de fora da tabela e por quê).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    arquivo = destino.with_suffix(".parquet")
    gravar_atomico(arquivo, lambda caminho: tabela.to_parquet(caminho, index=False))
    no_disco = ler_tabela(arquivo)
    manifesto = {
        "linhas": len(tabela),
        "sha256_da_tabela": hash_da_tabela(no_disco, ordem),
        "ordem": ordem,
        "origens": origens,
        "versao_do_codigo": versao_do_codigo(),
        **_conferencia_do_contrato(no_disco, destino),
        **(extras or {}),
    }
    texto = json.dumps(manifesto, ensure_ascii=False, indent=1)
    gravar_atomico(
        destino.with_suffix(".json"),
        lambda caminho: Path(caminho).write_text(texto, encoding="utf-8"),
    )
    return arquivo


def ler_tabela(arquivo: Path) -> pd.DataFrame:
    return pd.read_parquet(arquivo)


def conferir_tabela(arquivo: Path) -> bool:
    """O Parquet ainda tem o hash anotado no manifesto? (False sem manifesto)"""
    manifesto = arquivo.with_suffix(".json")
    if not manifesto.exists():
        return False
    anotado = json.loads(manifesto.read_text(encoding="utf-8"))
    return anotado.get("sha256_da_tabela") == hash_da_tabela(
        ler_tabela(arquivo), anotado.get("ordem", [])
    )


# --- versões: quando a fonte regrava um arquivo, a tabela anterior fica guardada ----------------
GRAVADO, IGUAL, ACRESCIDO = "gravado", "igual", "acrescido"
VERSAO_GUARDADA = re.compile(
    r"\.v\d+$"
)  # `2024.v1.parquet`: a tabela de antes, guardada


def arquivos_atuais(pasta: Path) -> list[Path]:
    """Os Parquets de uma pasta da base, sem as versões guardadas (`2024.v1.parquet`)."""
    return sorted(
        arquivo
        for arquivo in pasta.glob("*.parquet")
        if not VERSAO_GUARDADA.search(arquivo.stem)
    )


def origem_de_tabela(arquivo: Path, raiz: Path) -> dict[str, str]:
    """A origem de uma tabela derivada: o caminho da tabela de entrada na base e o hash do manifesto
    dela (ou do arquivo, se ela ainda não tem manifesto)."""
    manifesto = arquivo.with_suffix(".json")
    sha256 = (
        json.loads(manifesto.read_text(encoding="utf-8"))["sha256_da_tabela"]
        if manifesto.exists()
        else hashlib.sha256(arquivo.read_bytes()).hexdigest()
    )
    return {"url": arquivo.relative_to(raiz).as_posix(), "sha256": sha256}


# colunas que dizem de onde, quando e com que código a linha foi montada: não são o dado (ADR 0078)
LINHAGEM = ("origem_sha256", "origem_coletada_em", "montado_em", "versao_do_codigo")


def e_tabela_da_base(url: str) -> bool:
    """A origem é outra tabela da base (`cda/2025.parquet`), não um arquivo coletado ou conferido."""
    return url.endswith(".parquet") and "://" not in url


def origens_gravadas(destino: Path) -> list[dict[str, str]] | None:
    """As origens anotadas no manifesto de `destino` (None se ainda não foi gravado)."""
    manifesto = destino.with_suffix(".json")
    if not manifesto.exists():
        return None
    return json.loads(manifesto.read_text(encoding="utf-8")).get("origens")


def _hash_gravado(destino: Path) -> str | None:
    manifesto = destino.with_suffix(".json")
    return json.loads(manifesto.read_text(encoding="utf-8")).get("sha256_da_tabela")


def guardar_versao_anterior(destino: Path) -> Path:
    """`<destino>.parquet` e `.json` viram `<destino>.v<N>`, com o primeiro N livre."""
    n = 1
    while destino.with_name(f"{destino.name}.v{n}.parquet").exists():
        n += 1
    versao = destino.with_name(f"{destino.name}.v{n}")
    for extensao in (".parquet", ".json"):
        anterior = destino.with_name(destino.name + extensao)
        if (
            anterior.exists()
        ):  # tabela gravada antes do manifesto (ADR 0078) não tem o .json
            anterior.rename(versao.with_name(versao.name + extensao))
    log.info(
        "%s mudou na fonte: a versão anterior ficou como %s", destino.name, versao.name
    )
    return versao


def gravar_com_versoes(
    montar: Callable[[], pd.DataFrame],
    destino: Path,
    origens: list[dict[str, str]],
    ordem: list[str],
    *,
    forcar: bool = False,
) -> str:
    """Grava a tabela se o conteúdo mudou (`GRAVADO`), guardando a anterior; senão, `IGUAL`.

    `forcar`: monta e compara mesmo com as mesmas origens (o leitor mudou: corrigir o código não refaz
    o que já está gravado, lição do #333); se o conteúdo mudou, a anterior vira versão, como sempre.

    `montar` só é chamada quando precisa: com as mesmas origens, nada é lido nem regravado. Com
    origens novas e o mesmo conteúdo (o BC devolve o cadastro do IF.data com outros bytes), fica a
    tabela atual com o original anterior, que continua no acervo: versão só quando o dado muda.

    Se alguma origem é uma tabela da base (tabela derivada, como o painel dos fundos), a anterior não
    fica guardada (é sobrescrita na carga dela): com o mesmo conteúdo, o manifesto passa a apontar as
    origens novas, sem versão nova, para a linhagem continuar chegando aos originais (série 4).
    """
    anteriores = origens_gravadas(destino)
    if anteriores == origens and not forcar:
        return IGUAL
    tabela = montar()
    if anteriores is not None:
        if _hash_gravado(destino) == hash_da_tabela(como_no_disco(tabela), ordem):
            if any(e_tabela_da_base(o["url"]) for o in origens):
                gravar_tabela(tabela, destino, origens, ordem)
            return IGUAL
        guardar_versao_anterior(destino)
    gravar_tabela(tabela, destino, origens, ordem)
    return GRAVADO


def _sem_carimbos(tabela: pd.DataFrame, carimbos: Sequence[str]) -> pd.DataFrame:
    return tabela.drop(columns=[c for c in carimbos if c in tabela.columns])


def so_acrescentou(anterior: pd.DataFrame, nova: pd.DataFrame) -> bool:
    """Toda linha de `anterior` continua em `nova` (as mesmas colunas, nenhuma linha mudada ou tirada)."""
    if set(anterior.columns) != set(nova.columns):
        return False
    antes = pd.util.hash_pandas_object(anterior[list(nova.columns)], index=False)
    depois = pd.util.hash_pandas_object(nova, index=False).value_counts()
    contagem = antes.value_counts()
    return bool(contagem.le(depois.reindex(contagem.index, fill_value=0)).all())


def gravar_se_mudou(
    tabela: pd.DataFrame,
    destino: Path,
    origens: list[dict[str, str]],
    ordem: list[str],
    *,
    carimbos: Sequence[str] = (),
    versoes: bool = True,
) -> str:
    """Grava `<destino>.parquet` com manifesto, sem regravar o que não mudou (ADR 0078).

    Para tabelas que se remontam ou crescem (série B, curva, cripto), sem os `carimbos` (colunas de
    linhagem como `montado_em`, que mudam a cada montagem):
    - o mesmo dado, já com manifesto: nada é regravado (`IGUAL`), a linhagem fica a da primeira vez;
    - só linhas novas: regrava sem versão (`ACRESCIDO`), porque o passado não mudou;
    - uma linha antiga mudou ou sumiu: a tabela anterior vira `.vN` e a nova é gravada (`GRAVADO`).
      Com `versoes=False` (cripto, onde "a última vence" de propósito a cada rodada) só regrava.
    Tabela gravada antes do manifesto, ou com manifesto que não confere, ganha um certo na primeira
    remontagem.
    """
    destino = destino.with_suffix("")  # aceita `2024` ou `2024.parquet`
    arquivo = destino.with_suffix(".parquet")
    if not arquivo.exists():
        gravar_tabela(tabela, destino, origens, ordem)
        return GRAVADO
    antes = _sem_carimbos(ler_tabela(arquivo), carimbos)
    agora = _sem_carimbos(como_no_disco(tabela), carimbos)
    if set(antes.columns) == set(agora.columns) and hash_da_tabela(
        antes[list(agora.columns)], ordem
    ) == hash_da_tabela(agora, ordem):
        if conferir_tabela(
            arquivo
        ):  # manifesto que não confere (ou falta) é refeito, sem versão
            return IGUAL
        gravar_tabela(tabela, destino, origens, ordem)
        return GRAVADO
    if so_acrescentou(antes, agora):
        gravar_tabela(tabela, destino, origens, ordem)
        return ACRESCIDO
    if versoes:
        guardar_versao_anterior(destino)
    gravar_tabela(tabela, destino, origens, ordem)
    return GRAVADO


# --- lápide: oposição ou eliminação atendida (ADR 0077, item 2; plano, D7) -----------------------
def versoes_da_tabela(destino: Path) -> list[Path]:
    """A tabela vigente e as versões guardadas dela (`<nome>.v1.parquet`, `.v2`...), as que existem."""
    destino = destino.with_suffix("")
    guardadas = sorted(
        (
            a
            for a in destino.parent.glob(f"{destino.name}.v*.parquet")
            if a.stem.rsplit(".", 1)[0] == destino.name
            and VERSAO_GUARDADA.search(a.stem)
        ),
        key=lambda a: int(a.stem.rsplit(".v", 1)[1]),
    )
    vigente = destino.with_suffix(".parquet")
    return [vigente, *guardadas] if vigente.exists() else guardadas


def _sem_os_ids(tabela: pd.DataFrame, ids: set[str]) -> pd.DataFrame | None:
    """A tabela com cada valor de `ids` trocado por vazio; None se nenhum aparece."""
    textos = [
        c
        for c in tabela.columns
        if tabela[c].dtype == object or pd.api.types.is_string_dtype(tabela[c])
    ]
    achados = {c: tabela[c].isin(ids) for c in textos}
    if not any(a.any() for a in achados.values()):
        return None
    tabela = tabela.copy()
    for coluna, achado in achados.items():
        if achado.any():
            tabela[coluna] = tabela[coluna].astype(object).mask(achado, None)
    return tabela


def regravar_por_lapide(destino: Path, ids_pessoa: set[str], dia: str) -> list[Path]:
    """Regrava a vigente e as versões `.vN` de `destino` sem os `ids_pessoa` (a única exceção ao
    "nada é apagado"). Devolve os Parquets regravados.

    A linha fica, com o id trocado por vazio: a aresta vira um fato anônimo da empresa. O hash do
    manifesto é refeito e `regravada_por_lapide` ganha o dia (nunca o id). A tabela regravada continua
    conferindo; a derivada que a usava deixa de conferir até ser remontada. Só valores inteiros de
    coluna de texto (um id dentro de uma lista em texto não é achado: as tabelas da rede não têm).
    """
    regravadas = []
    for arquivo in versoes_da_tabela(destino) if ids_pessoa else []:
        tabela = _sem_os_ids(ler_tabela(arquivo), set(ids_pessoa))
        if tabela is None:
            continue
        gravar_atomico(
            arquivo, lambda caminho, t=tabela: t.to_parquet(caminho, index=False)
        )
        manifesto = arquivo.with_suffix(".json")
        if manifesto.exists():
            anotado = json.loads(manifesto.read_text(encoding="utf-8"))
            anotado["sha256_da_tabela"] = hash_da_tabela(
                ler_tabela(arquivo), anotado.get("ordem", [])
            )
            anotado["regravada_por_lapide"] = [
                *anotado.get("regravada_por_lapide", []),
                {"dia": dia, "versao_do_codigo": versao_do_codigo()},
            ]
            texto = json.dumps(anotado, ensure_ascii=False, indent=1)
            gravar_atomico(
                manifesto,
                lambda caminho, x=texto: Path(caminho).write_text(x, encoding="utf-8"),
            )
        log.info("%s regravada pela lápide de %s", arquivo.name, dia)
        regravadas.append(arquivo)
    return regravadas
