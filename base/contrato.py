"""Contrato de dados com versão e catálogo da base (ADR 0077, PR 1).

O dicionário (`base/dicionario.py`) diz o que cada tabela é; aqui ele vira três coisas que quem
consome a base (o app, o Capital, um parceiro) pode confiar:

- `base/contratos/catalogo.json`: uma entrada por tabela com módulo, dono, versão, colunas, chaves,
  as três datas, histórico, licença e revenda (gerado, o teste reclama se estiver velho);
- `base/contratos/v<maior>/<tabela>.json`: o contrato **congelado** da versão maior. O gerador
  nunca regrava um que já exista: mudar o contrato de verdade exige subir a versão maior;
- `docs/CHANGELOG-da-base.md`: o que mudou em cada tabela desde o contrato congelado.

Regra das versões (`conferir_versoes`, que o CI roda): coluna que some, unidade que muda ou chave
que muda exigem versão **maior** (1.x.x → 2.0.0); coluna nova exige ao menos a **menor** (1.0.0 →
1.1.0). Gerar tudo: `python -m base.contrato`.
"""

import json
from pathlib import Path

from base.dicionario import TABELAS, Tabela
from base.tempo import sinonimos_de_tempo
from src.banco.coletas import licenca_da_fonte, revenda_da_fonte

RAIZ = Path(__file__).resolve().parent.parent
PASTA = Path(__file__).resolve().parent / "contratos"
ARQUIVO_DO_CHANGELOG = RAIZ / "docs" / "CHANGELOG-da-base.md"
DONO = "Dados"  # mesa dona de todas as tabelas de hoje (ADR 0076, D1)


def versao_em_numeros(versao: str) -> tuple[int, int, int]:
    partes = versao.split(".")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        raise ValueError(
            f"versão do contrato inválida: {versao!r} (use maior.menor.correção)"
        )
    return int(partes[0]), int(partes[1]), int(partes[2])


def contrato_da_tabela(nome: str, tabela: Tabela) -> dict:
    return {
        "tabela": nome,
        "modulo": tabela.modulo,
        "dono": DONO,
        "versao": tabela.versao_do_contrato,
        "colunas": {
            coluna: {"descricao": descricao, "unidade": unidade}
            for coluna, (descricao, unidade) in tabela.colunas.items()
        },
        "chaves": list(tabela.chaves),
        "datas": dict(tabela.datas),
        "sinonimos_de_tempo": sinonimos_de_tempo(tabela),
        "historico_desde": tabela.historico_desde,
        "granularidade_do_publico_em": tabela.granularidade_do_publico_em,
        "licenca": licenca_da_fonte(tabela.familia_da_fonte),
        "revenda": revenda_da_fonte(tabela.familia_da_fonte),
        "pessoa": tabela.pessoa,
        "frequencia": tabela.frequencia,
        "atraso": tabela.atraso,
        # só quando há: o catálogo das tabelas que nunca renomearam nada não muda
        **({"renomeadas": dict(tabela.renomeadas)} if tabela.renomeadas else {}),
    }


def catalogo(tabelas: dict[str, Tabela] = TABELAS) -> dict:
    return {
        "tabelas": {nome: contrato_da_tabela(nome, t) for nome, t in tabelas.items()},
    }


def _congelado(pasta: Path, nome: str) -> dict | None:
    """O contrato congelado mais novo da tabela (a maior versão que tem arquivo dela)."""
    pastas = sorted(
        (p for p in pasta.glob("v*") if p.is_dir() and p.name[1:].isdigit()),
        key=lambda p: int(p.name[1:]),
        reverse=True,
    )
    for p in pastas:
        arquivo = p / f"{nome}.json"
        if arquivo.exists():
            return json.loads(arquivo.read_text(encoding="utf-8"))
    return None


def _diferencas(antigo: dict, novo: dict) -> dict[str, list[str]]:
    colunas_antigas, colunas_novas = antigo["colunas"], novo["colunas"]
    return {
        "sumiram": sorted(set(colunas_antigas) - set(colunas_novas)),
        "novas": sorted(set(colunas_novas) - set(colunas_antigas)),
        "unidade": sorted(
            c
            for c in set(colunas_antigas) & set(colunas_novas)
            if colunas_antigas[c]["unidade"] != colunas_novas[c]["unidade"]
        ),
        "chaves": [] if antigo["chaves"] == novo["chaves"] else list(novo["chaves"]),
    }


def conferir_versoes(tabelas: dict[str, Tabela], pasta: Path = PASTA) -> list[str]:
    """Erros (um por problema) entre o dicionário e o contrato congelado; lista vazia = em dia."""
    erros: list[str] = []
    nomes_congelados = {
        arquivo.stem
        for arquivo in pasta.glob("v*/*.json")
        if arquivo.parent.name[1:].isdigit()
    }
    erros.extend(
        f"{nome}: a tabela sumiu do dicionário (contrato congelado existe)"
        for nome in sorted(nomes_congelados - set(tabelas))
    )
    for nome, tabela in tabelas.items():
        antigo = _congelado(pasta, nome)
        if antigo is None:
            continue  # tabela nova: o gerador congela a v1
        atual = versao_em_numeros(tabela.versao_do_contrato)
        anterior = versao_em_numeros(antigo["versao"])
        d = _diferencas(antigo, contrato_da_tabela(nome, tabela))
        if (
            any(d[k] for k in ("sumiram", "unidade", "chaves"))
            and atual[0] <= anterior[0]
        ):
            detalhe = []
            if d["sumiram"]:
                detalhe.append(f"colunas que sumiram: {', '.join(d['sumiram'])}")
            if d["unidade"]:
                detalhe.append(f"unidade mudou: {', '.join(d['unidade'])}")
            if d["chaves"]:
                detalhe.append("as chaves mudaram")
            erros.append(
                f"{nome}: {'; '.join(detalhe)}; suba a versão maior "
                f"({anterior[0] + 1}.0.0), hoje {tabela.versao_do_contrato}"
            )
        elif d["novas"] and atual <= anterior:
            erros.append(
                f"{nome}: colunas novas ({', '.join(d['novas'])}); suba ao menos a versão menor "
                f"({anterior[0]}.{anterior[1] + 1}.0), hoje {tabela.versao_do_contrato}"
            )
    return erros


def changelog(tabelas: dict[str, Tabela], pasta: Path = PASTA) -> str:
    linhas = [
        "# Mudanças no contrato da base",
        "",
        "Gerado por `python -m base.contrato` (não edite à mão). Compara o dicionário com o contrato",
        "congelado de cada tabela (`base/contratos/v<maior>/`). Versão maior: coluna que some ou",
        "muda de unidade ou de chave; menor: coluna nova; correção: dado.",
        "",
    ]
    mudou = False
    for nome, tabela in tabelas.items():
        antigo = _congelado(pasta, nome)
        if antigo is None:
            continue
        d = _diferencas(antigo, contrato_da_tabela(nome, tabela))
        if not any(d.values()) and antigo["versao"] == tabela.versao_do_contrato:
            continue
        mudou = True
        linhas.append(f"- `{nome}`: {antigo['versao']} → {tabela.versao_do_contrato}")
        for chave, rotulo in (
            ("novas", "colunas novas"),
            ("sumiram", "colunas removidas"),
            ("unidade", "unidade mudou"),
        ):
            if d[chave]:
                linhas.append(f"  - {rotulo}: {', '.join(f'`{c}`' for c in d[chave])}")
        if d["chaves"]:
            linhas.append("  - chaves mudaram")
    if not mudou:
        linhas.append(
            f"Nenhuma mudança: as {len(tabelas)} tabelas estão no contrato congelado (v1.0.0)."
        )
    return "\n".join(linhas) + "\n"


def _escrever(caminho: Path, texto: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # fim de linha LF também no Windows: o teste compara com o mesmo texto no Linux do CI
    caminho.write_text(texto, encoding="utf-8", newline="\n")


def _json(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2) + "\n"


def gravar(
    tabelas: dict[str, Tabela] = TABELAS,
    pasta: Path = PASTA,
    arquivo_do_changelog: Path = ARQUIVO_DO_CHANGELOG,
) -> None:
    """Grava o catálogo e o changelog; cria o contrato da versão maior só se ainda não existir."""
    _escrever(pasta / "catalogo.json", _json(catalogo(tabelas)))
    for nome, tabela in tabelas.items():
        arquivo = (
            pasta
            / f"v{versao_em_numeros(tabela.versao_do_contrato)[0]}"
            / f"{nome}.json"
        )
        if not arquivo.exists():
            _escrever(arquivo, _json(contrato_da_tabela(nome, tabela)))
    _escrever(arquivo_do_changelog, changelog(tabelas, pasta))


if __name__ == "__main__":
    gravar()
    print(f"contratos gravados em {PASTA}")
