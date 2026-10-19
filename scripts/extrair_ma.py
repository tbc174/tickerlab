"""A extração de M&A medida na amostra de ouro (série 1, PR 2 do plano da base de M&A).

    python -m scripts.extrair_ma estimar --ouro CSV --textos P --saida S [--modelo M]   (sem API)
    python -m scripts.extrair_ma enviar  --ouro CSV --textos P --saida S --teto-dolares 3 [--modelo M]
    python -m scripts.extrair_ma buscar  --ouro CSV --textos P --saida S [--modelo M]
    python -m scripts.extrair_ma medir   --ouro CSV --textos P --saida S                (sem API)
    python -m scripts.extrair_ma operacoes|multiplos --ouro CSV --textos P --saida S    (sem API)
    python -m scripts.extrair_ma base-estimar --candidatos PARQUET --textos P --saida S --limite N [--teto-dolares T]
    python -m scripts.extrair_ma base-enviar  --candidatos PARQUET --textos P --saida S --limite N --teto-dolares T

Os passos `base-*` são o modo "base inteira": em vez da amostra de ouro, os candidatos de
`ma_candidatos` com texto já coletado (`<acervo>/ma/candidatos/candidatos.parquet`), na ordem da
coleta (`base.ma_textos.grupo`), sem repetir o que o manifesto já tem. Sempre com `--limite` de
documentos e `--teto-dolares` (o `base-enviar` recusa se a estimativa do lote passa do teto).

`--ouro` é a amostra de ouro (`tickerlab-fontes/ma/amostra_de_ouro_candidatas.csv`); `--textos`, a
pasta com o texto de cada documento (`<protocolo>.txt`). `enviar` manda um lote da Batch API (Haiku
5.5; `--modelo claude-sonnet-5-5` para a segunda leitura) e **gasta API**: só roda com o "pode" do
Tiago para o valor, e o teto (`--teto-dolares`, obrigatório) trava o envio antes de gastar. Cada
resposta fica guardada bruta, com tokens e custo; `medir` confere tudo de novo (`base.ma_extracao`)
e compara com a amostra, por modelo, com o custo por documento e as divergências entre os dois.
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from itertools import islice
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import pandas as pd
import sqlalchemy as sa

from base import ma_extracao as mx
from base import ma_multiplos as mm
from base import ma_operacoes as mo
from base import ma_textos as mt
from base.historico import ano_do_arquivo
from base.parquet import ler_tabela
from scripts.rotular_com_ia import TetoPassado
from src import acervo
from src import demonstracoes as dm
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import obter_engine

log = logging.getLogger("tickerlab.extrair_ma")
FUSO = ZoneInfo("America/Sao_Paulo")
VARIAVEL_DA_CHAVE = "ANTHROPIC_API_KEY_MA"
MODELOS = (mx.MODELO, mx.CONFERENTE)


@dataclass(frozen=True)
class Documento:
    protocolo: str
    publico_em: date
    texto: str


@dataclass(frozen=True)
class Medida:
    modelo: str
    placar: pd.DataFrame
    lidos: int
    custo_por_documento: float
    leituras: dict[str, mx.LeituraDaOperacao]
    com_descarte: int
    para_revisao: int


def _ouro(arquivo: Path) -> pd.DataFrame:
    return pd.read_csv(arquivo, sep=";", encoding="utf-8-sig", dtype=str)


def documentos(ouro: Path, textos: Path) -> list[Documento]:
    """Os documentos da amostra com texto guardado (o vazio fica de fora: não há o que ler)."""
    achados = []
    for linha in _ouro(ouro).to_dict("records"):
        arquivo = textos / f"{mt.nome_do_texto(linha['Protocolo_Entrega'])}.txt"
        texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
        if texto.strip():
            achados.append(
                Documento(
                    linha["Protocolo_Entrega"],
                    date.fromisoformat(linha["Data_Entrega"][:10]),
                    texto,
                )
            )
    return achados


# --- leituras e manifesto guardados --------------------------------------------------------------


def _arquivo_das_leituras(saida: Path, modelo: str) -> Path:
    return saida / f"leituras-{modelo}.jsonl"


def _arquivo_do_manifesto(saida: Path, modelo: str) -> Path:
    return saida / f"manifesto-{modelo}.json"


def ler_leituras(saida: Path, modelo: str) -> dict[str, dict]:
    arquivo = _arquivo_das_leituras(saida, modelo)
    if not arquivo.exists():
        return {}
    registros = (
        json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines()
    )
    return {r["protocolo"]: r for r in registros}


def ler_manifesto(saida: Path, modelo: str) -> dict:
    arquivo = _arquivo_do_manifesto(saida, modelo)
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}


def _gravar_manifesto(saida: Path, modelo: str, manifesto: dict) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    _arquivo_do_manifesto(saida, modelo).write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _acrescentar(saida: Path, modelo: str, registros: list[dict]) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    with _arquivo_das_leituras(saida, modelo).open("a", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def pendentes(ouro: Path, textos: Path, saida: Path, modelo: str) -> list[Documento]:
    """Os documentos sem leitura boa deste modelo (os com erro entram de novo)."""
    feitas = ler_leituras(saida, modelo)
    return [
        d
        for d in documentos(ouro, textos)
        if d.protocolo not in feitas or "erro" in feitas[d.protocolo]
    ]


def conferir_teto(manifesto: dict, estimativa: float, teto: float) -> None:
    gasto = manifesto.get("gasto_em_dolares", 0.0)
    if gasto + estimativa > teto:
        raise TetoPassado(
            f"Gasto já feito US$ {gasto:.2f} + estimativa US$ {estimativa:.2f} passa do teto US$ {teto:.2f}."
        )


def _custo(usage: anthropic.types.Usage, modelo: str) -> float:
    entrada = (
        (usage.input_tokens or 0)
        + mx.PESO_DA_ESCRITA_NO_CACHE * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + mx.preco(modelo).leitura_do_cache * (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )  # fmt: skip
    return mx.custo_em_dolares(entrada, usage.output_tokens or 0, modelo=modelo)


# --- enviar e buscar (gastam API) ------------------------------------------------------------------


def enviar(
    cliente: anthropic.Anthropic, ouro: Path, textos: Path, saida: Path, modelo: str, teto: float
) -> str | None:  # fmt: skip
    """Manda os pendentes da amostra de ouro num lote da Batch API, se o teto permitir."""
    return enviar_documentos(
        cliente, pendentes(ouro, textos, saida, modelo), saida, modelo, teto
    )


def enviar_documentos(
    cliente: anthropic.Anthropic,
    fila: list[Documento],
    saida: Path,
    modelo: str,
    teto: float,
) -> str | None:
    """Manda a `fila` num lote da Batch API, se o teto permitir. Devolve o id do lote."""
    manifesto = ler_manifesto(saida, modelo)
    if any(lote["estado"] != "gravado" for lote in manifesto.get("lotes", [])):
        raise RuntimeError(
            "Há um lote enviado e ainda não gravado: rode `buscar` primeiro."
        )
    if not fila:
        log.info("Nada pendente para %s.", modelo)
        return None
    estimativa = mx.estimar_custo([d.texto for d in fila], modelo)
    conferir_teto(manifesto, estimativa, teto)
    lote = cliente.messages.batches.create(
        requests=[
            {
                "custom_id": mt.nome_do_texto(d.protocolo),
                "params": mx.pedido(d.texto, modelo),
            }
            for d in fila
        ]
    )
    # o id do lote não aceita o link que é o protocolo dos documentos antigos: guarda a volta
    protocolos = {
        mt.nome_do_texto(d.protocolo): d.protocolo
        for d in fila
        if mt.nome_do_texto(d.protocolo) != d.protocolo
    }
    manifesto["lotes"] = [
        *manifesto.get("lotes", []),
        {"id": lote.id, "documentos": len(fila), "estimativa": estimativa, "estado": "enviado",
         "enviado_em": datetime.now(FUSO).isoformat(timespec="seconds"), "protocolos": protocolos},
    ]  # fmt: skip
    _gravar_manifesto(saida, modelo, manifesto)
    log.info(
        "Lote %s: %s documentos, estimativa US$ %.2f", lote.id, len(fila), estimativa
    )
    return lote.id


def buscar(cliente: anthropic.Anthropic, saida: Path, modelo: str) -> int:
    """Grava as respostas brutas dos lotes que terminaram, com tokens e custo. Devolve quantas."""
    manifesto = ler_manifesto(saida, modelo)
    gravadas = 0
    for lote in manifesto.get("lotes", []):
        if lote["estado"] == "gravado":
            continue
        if cliente.messages.batches.retrieve(lote["id"]).processing_status != "ended":
            log.info("Lote %s ainda processando.", lote["id"])
            continue
        registros, gasto = [], 0.0
        for resultado in cliente.messages.batches.results(lote["id"]):
            protocolo = lote.get("protocolos", {}).get(
                resultado.custom_id, resultado.custom_id
            )
            base = {"protocolo": protocolo, "modelo": modelo, "lote": lote["id"],
                    "versao_do_guia": mx.VERSAO_DO_GUIA,
                    "lido_em": datetime.now(FUSO).isoformat(timespec="seconds")}  # fmt: skip
            if resultado.result.type != "succeeded":
                registros.append(base | {"erro": f"lote: {resultado.result.type}"})
                continue
            mensagem = resultado.result.message
            custo = _custo(mensagem.usage, modelo)
            gasto += custo
            bruta = next((b.text for b in mensagem.content if b.type == "text"), "")
            registro = base | {
                "resposta_bruta": bruta,
                "tokens_entrada": mensagem.usage.input_tokens,
                "tokens_saida": mensagem.usage.output_tokens,
                "custo": custo,
            }
            if mensagem.stop_reason != "end_turn":
                registro["erro"] = f"parada: {mensagem.stop_reason}"
            registros.append(registro)
        _acrescentar(saida, modelo, registros)
        lote |= {"estado": "gravado", "gasto": gasto}
        manifesto["gasto_em_dolares"] = manifesto.get("gasto_em_dolares", 0.0) + gasto
        gravadas += len(registros)
    _gravar_manifesto(saida, modelo, manifesto)
    return gravadas


# --- modo base inteira (sem API) ---------------------------------------------------------------------


def documentos_da_base(candidatos: Path, textos: Path) -> list[Documento]:
    """Os candidatos da base com texto guardado, na ordem da coleta (o grupo que mais rende primeiro,
    do mais novo ao mais velho). Reentregas com o mesmo protocolo dividem o texto: fica a mais nova."""
    tabela = ler_tabela(candidatos)
    tabela["_grupo"] = mt.grupo(tabela)
    tabela = tabela.sort_values(
        ["_grupo", "publico_em", "protocolo", "versao"],
        ascending=[True, False, False, False],
        kind="stable",
    ).drop_duplicates("protocolo")
    achados = []
    for linha in tabela.itertuples(index=False):
        arquivo = textos / f"{mt.nome_do_texto(linha.protocolo)}.txt"
        texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
        if texto.strip():
            achados.append(
                Documento(linha.protocolo, pd.Timestamp(linha.publico_em).date(), texto)
            )
    return achados


def pendentes_da_base(
    candidatos: Path, textos: Path, saida: Path, modelo: str, limite: int
) -> list[Documento]:
    """Os primeiros `limite` documentos da base sem leitura boa deste modelo (os com erro entram de
    novo)."""
    feitas = ler_leituras(saida, modelo)
    sem_leitura = (
        d
        for d in documentos_da_base(candidatos, textos)
        if d.protocolo not in feitas or "erro" in feitas[d.protocolo]
    )
    return list(islice(sem_leitura, limite))


def quantos_cabem(fila: list[Documento], modelo: str, verba: float) -> int:
    """Quantos documentos do começo da `fila` cabem na `verba` (US$), pela mesma estimativa do envio."""
    cabem = 0
    for fim in range(1, len(fila) + 1):
        if mx.estimar_custo([d.texto for d in fila[:fim]], modelo) > verba:
            break
        cabem = fim
    return cabem


# --- medida (sem API) -------------------------------------------------------------------------------


def medir_modelo(ouro: Path, textos: Path, saida: Path, modelo: str) -> Medida:
    """Confere de novo as respostas guardadas (a regra pode ter mudado; não paga de novo) e compara
    com a amostra de ouro."""
    guardadas = ler_leituras(saida, modelo)
    leituras: dict[str, mx.LeituraDaOperacao] = {}
    com_descarte = para_revisao = 0
    for documento in documentos(ouro, textos):
        registro = guardadas.get(documento.protocolo)
        if registro is None or "erro" in registro:
            continue
        try:
            lida = mx.LeituraDaOperacao.model_validate_json(registro["resposta_bruta"])
        except ValueError:
            continue
        conferida = mx.conferir(lida, documento.texto, documento.publico_em)
        leituras[documento.protocolo] = conferida.leitura
        com_descarte += bool(conferida.descartes)
        para_revisao += conferida.precisa_de_revisao
    gasto = ler_manifesto(saida, modelo).get("gasto_em_dolares", 0.0)
    return Medida(
        modelo,
        mx.medir(leituras, _ouro(ouro)),
        len(leituras),
        gasto / len(leituras) if leituras else 0.0,
        leituras,
        com_descarte,
        para_revisao,
    )


def _leitura_do_gabarito(linha: dict) -> mx.LeituraDaOperacao | None:
    """A resposta conferida à mão no formato da leitura (só o que a ligação usa)."""
    partes = [
        {"nome": linha[papel], "papel": papel, "trecho": linha[papel]}
        for papel in ("alvo", "comprador")
        if isinstance(linha.get(papel), str) and linha[papel].strip()
    ]
    try:
        return mx.LeituraDaOperacao.model_validate(
            {"tipo": linha.get("tipo_conferido"), "partes": partes}
        )
    except ValueError:
        return None


def operacoes_da_amostra(
    ouro: Path, textos: Path, saida: Path, modelo: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[list[str]]]]:
    """As operações montadas das leituras guardadas (PR 3 do plano) e a comparação com a ligação
    das respostas do gabarito pela mesma regra: duplicada é par que o gabarito junta e a leitura
    separa."""
    datas = {d.protocolo: d.publico_em for d in documentos(ouro, textos)}
    lidos = [
        mo.DocumentoLido(protocolo, datas[protocolo], leitura)
        for protocolo, leitura in medir_modelo(
            ouro, textos, saida, modelo
        ).leituras.items()
    ]
    tabela, ligacoes = mo.operacoes(lidos)
    do_gabarito = []
    for linha in _ouro(ouro).to_dict("records"):
        protocolo = linha["Protocolo_Entrega"]
        leitura = _leitura_do_gabarito(linha)
        if protocolo in datas and leitura is not None:
            do_gabarito.append(mo.DocumentoLido(protocolo, datas[protocolo], leitura))
    comparacao = mo.comparar(mo.ligar(lidos), mo.ligar(do_gabarito))
    return tabela, ligacoes, comparacao


def emissoras_do_ouro(ouro: Path) -> dict[str, mm.Emissora]:
    """Quem entregou cada documento da amostra (as colunas do IPE)."""
    return {
        linha["Protocolo_Entrega"]: mm.Emissora(
            linha["CNPJ_Companhia"], linha["Nome_Companhia"]
        )
        for linha in _ouro(ouro).to_dict("records")
    }


def demonstracoes_do_acervo(
    conexao: sa.Connection, cnpjs: set[str], anos: set[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(contas, documentos) dos DFP e ITR guardados pelo arquivista (`cvm-hist-dfp`, `cvm-hist-itr`),
    só das companhias e dos anos pedidos (não baixa nada)."""
    contas, indices = [], []
    for documento, fonte in (("DFP", "cvm-hist-dfp"), ("ITR", "cvm-hist-itr")):
        for original in originais_mais_recentes(conexao, fonte):
            if ano_do_arquivo(original.url) not in anos:
                continue
            conteudo = acervo.ler_original(original.caminho_do_original)
            if conteudo is None:
                continue
            do_ano, indice = dm.ler_demonstracoes(conteudo, documento)
            contas.append(do_ano[do_ano["cnpj"].isin(cnpjs)])
            indices.append(indice[indice["cnpj"].isin(cnpjs)])
    if not contas:
        return pd.DataFrame(columns=dm.COLUNAS), pd.DataFrame(
            columns=["cnpj", "documento", "referencia", "versao", "recebido_em"]
        )
    return pd.concat(contas, ignore_index=True), pd.concat(indices, ignore_index=True)


def multiplos_da_amostra(
    conexao: sa.Connection, ouro: Path, textos: Path, saida: Path, modelo: str
) -> pd.DataFrame:
    """Os múltiplos implícitos das operações da amostra (PR 4 do plano), das leituras guardadas."""
    datas = {d.protocolo: d.publico_em for d in documentos(ouro, textos)}
    lidos = [
        mo.DocumentoLido(protocolo, datas[protocolo], leitura)
        for protocolo, leitura in medir_modelo(
            ouro, textos, saida, modelo
        ).leituras.items()
    ]
    emissoras = emissoras_do_ouro(ouro)
    # o ano do anúncio e o anterior: o DFP do ano passado e o ITR deste dão os 12 meses
    anos = {ano for dia in datas.values() for ano in (dia.year - 1, dia.year)}
    contas, entregues = demonstracoes_do_acervo(
        conexao, {e.cnpj for e in emissoras.values()}, anos
    )
    return mm.multiplos(lidos, emissoras, contas, entregues)


def relatorio_dos_multiplos(modelo: str, tabela: pd.DataFrame) -> str:
    com = tabela[tabela[["ev_receita", "ev_ebit", "p_l", "p_vp"]].notna().any(axis=1)]
    motivos = tabela.loc[tabela["motivo"].fillna("") != "", "motivo"].value_counts()
    colunas = ["alvo", "anuncio", "valor_campo", "base_12m", "entregue_ate",
               "ev_receita", "ev_ebit", "p_l", "p_vp"]  # fmt: skip
    return (
        f"## Múltiplos implícitos ({modelo})\n\n{len(com)} de {len(tabela)} operações com algum "
        f"múltiplo; todos de documentos entregues antes do anúncio.\n\nSem múltiplo, por "
        f"motivo:\n\n{motivos.to_string()}\n\n{com.loc[:, colunas].to_string(index=False)}\n"
    )


def relatorio_das_operacoes(
    modelo: str, tabela: pd.DataFrame, comparacao: dict[str, list[list[str]]]
) -> str:
    varios = tabela[tabela["documentos"] > 1]
    return (
        f"## Operações ({modelo})\n\n{sum(tabela['documentos'].tolist())} documentos de operação "
        f"viraram {len(tabela)} operações; {len(varios)} com mais de um documento.\n\n"
        f"Pares do gabarito: {comparacao['no_gabarito']}\n\n"
        f"Duplicadas (o gabarito junta, a leitura separa): {comparacao['separadas'] or 'nenhuma'}"
        f"\n\nJuntadas por engano: {comparacao['juntadas'] or 'nenhuma'}\n\n"
        f"{varios.to_string(index=False) if len(varios) else ''}\n"
    )


def relatorio(medidas: list[Medida]) -> str:
    """O placar por modelo, o custo por documento e onde as duas leituras discordam."""
    partes = [
        f"## {m.modelo}\n\n{m.lidos} documentos lidos; US$ {m.custo_por_documento:.5f} por "
        f"documento (lote); {m.com_descarte} com algum item descartado; {m.para_revisao} para "
        f"revisão pela coerência.\n\n{m.placar.to_string(index=False)}\n"
        for m in medidas
    ]
    if len(medidas) == 2:
        a, b = medidas
        comuns = sorted(set(a.leituras) & set(b.leituras))
        contagem: dict[str, int] = {}
        for protocolo in comuns:
            for campo in mx.divergencias(a.leituras[protocolo], b.leituras[protocolo]):
                contagem[campo] = contagem.get(campo, 0) + 1
        partes.append(
            f"## As duas leituras\n\n{len(comuns)} documentos lidos pelos dois; divergências por "
            f"campo (vão para revisão humana): {contagem or 'nenhuma'}\n"
        )
    return "\n".join(partes)


def cliente_de_ma() -> anthropic.Anthropic:
    """O cliente da API com a chave só da base de M&A (ADR 0087, regra 2: uma chave por uso). Sem a
    variável própria, o script para antes de qualquer chamada."""
    chave = os.environ.get(VARIAVEL_DA_CHAVE, "").strip()
    if not chave:
        raise SystemExit(
            f"Falta {VARIAVEL_DA_CHAVE} no ambiente (a chave da base de M&A): rode "
            "projeto-acoes/configurar-chave-anthropic-ma-casa.ps1."
        )
    return anthropic.Anthropic(api_key=chave)


def _argumentos() -> argparse.ArgumentParser:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    sub = argumentos.add_subparsers(dest="passo", required=True)
    for nome, ajuda in (
        ("estimar", "custo projetado em US$ (sem API)"),
        ("enviar", "manda o lote da Batch API (GASTA API)"),
        ("buscar", "grava os lotes que terminaram"),
        ("medir", "compara com a amostra de ouro (sem API)"),
        (
            "operacoes",
            "liga os documentos da mesma operação e confere no gabarito (sem API)",
        ),
        (
            "multiplos",
            "múltiplos implícitos com o balanço de antes do anúncio (sem API)",
        ),
    ):
        passo = sub.add_parser(nome, help=ajuda)
        passo.add_argument("--ouro", type=Path, required=True)
        passo.add_argument("--textos", type=Path, required=True)
        passo.add_argument("--saida", type=Path, required=True)
        passo.add_argument("--modelo", default=mx.MODELO, choices=MODELOS)
        if nome == "enviar":
            passo.add_argument("--teto-dolares", type=float, required=True)
    for nome, ajuda in (
        ("base-estimar", "custo projetado de um lote da base inteira (sem API)"),
        ("base-enviar", "manda um lote da base inteira (GASTA API)"),
    ):
        passo = sub.add_parser(nome, help=ajuda)
        passo.add_argument("--candidatos", type=Path, required=True)
        passo.add_argument("--textos", type=Path, required=True)
        passo.add_argument("--saida", type=Path, required=True)
        passo.add_argument("--modelo", default=mx.MODELO, choices=MODELOS)
        passo.add_argument("--limite", type=int, required=True)
        passo.add_argument("--teto-dolares", type=float, required=nome == "base-enviar")
    return argumentos


def _passo_da_base(opcoes: argparse.Namespace) -> int:
    fila = pendentes_da_base(
        opcoes.candidatos, opcoes.textos, opcoes.saida, opcoes.modelo, opcoes.limite
    )
    if opcoes.passo == "base-estimar":
        custo = mx.estimar_custo([d.texto for d in fila], opcoes.modelo)
        print(
            f"{opcoes.modelo}: {len(fila)} documentos, estimativa US$ {custo:.2f} (lote)"
        )
        if opcoes.teto_dolares is not None:
            gasto = ler_manifesto(opcoes.saida, opcoes.modelo).get(
                "gasto_em_dolares", 0.0
            )
            verba = max(opcoes.teto_dolares - gasto, 0.0)
            print(
                f"Cabem {quantos_cabem(fila, opcoes.modelo, verba)} no teto (US$ {verba:.2f} livres)"
            )
    else:
        enviar_documentos(
            cliente_de_ma(), fila, opcoes.saida, opcoes.modelo, opcoes.teto_dolares
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    opcoes = _argumentos().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.passo.startswith("base-"):
        return _passo_da_base(opcoes)
    ouro, textos, saida, modelo = (
        opcoes.ouro,
        opcoes.textos,
        opcoes.saida,
        opcoes.modelo,
    )
    if opcoes.passo == "estimar":
        for nome in MODELOS:
            fila = pendentes(ouro, textos, saida, nome)
            custo = mx.estimar_custo([d.texto for d in fila], nome)
            print(f"{nome}: {len(fila)} documentos, estimativa US$ {custo:.2f} (lote)")
    elif opcoes.passo == "medir":
        medidas = [medir_modelo(ouro, textos, saida, nome) for nome in MODELOS]
        texto = relatorio([m for m in medidas if m.lidos])
        (saida / "medida.md").write_text(texto, encoding="utf-8")
        print(texto)
    elif opcoes.passo == "operacoes":
        tabela, ligacoes, comparacao = operacoes_da_amostra(ouro, textos, saida, modelo)
        tabela.to_csv(saida / f"operacoes-{modelo}.csv", sep=";", index=False)
        ligacoes.to_csv(saida / f"ligacoes-{modelo}.csv", sep=";", index=False)
        texto = relatorio_das_operacoes(modelo, tabela, comparacao)
        (saida / f"operacoes-{modelo}.md").write_text(texto, encoding="utf-8")
        print(texto)
    elif opcoes.passo == "multiplos":
        with obter_engine().connect() as conexao:
            tabela = multiplos_da_amostra(conexao, ouro, textos, saida, modelo)
        tabela.to_csv(saida / f"multiplos-{modelo}.csv", sep=";", index=False)
        texto = relatorio_dos_multiplos(modelo, tabela)
        (saida / f"multiplos-{modelo}.md").write_text(texto, encoding="utf-8")
        print(texto)
    elif opcoes.passo == "enviar":
        enviar(cliente_de_ma(), ouro, textos, saida, modelo, opcoes.teto_dolares)
    else:
        print(f"{buscar(cliente_de_ma(), saida, modelo)} respostas gravadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
