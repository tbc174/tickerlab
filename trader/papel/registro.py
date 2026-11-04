"""A cadeia do papel: uma linha por dia e por série, com a data do relógio e o hash, sem regravar.

Cada série tem um arquivo `<serie>.jsonl` na pasta do papel (fora do Git). Cada linha é o JSON da
foto do dia (sinal e carteira), mais o que o registro põe: o dia em que o sinal vale, o prazo, a data
e a hora do relógio (Brasília), o hash da linha anterior e o próprio hash (SHA-256 do JSON canônico
sem o campo `hash`, como no registro dos agentes). Editar, apagar ou trocar a ordem de uma linha
quebra a cadeia, e `verificar` aponta onde.

Regras que o código faz cumprir (seção 5, P3):

- **um dia por linha, nunca regravado:** um dia igual ou anterior ao último da série é recusado;
- **antes do pregão em que valeria:** na B3, até o início da pré-abertura (09h45); em cripto, até a
  meia-noite de Brasília do dia (o "sinal à meia-noite de Brasília" da seção 3). Depois do prazo o
  dia só entra como falta;
- **só depois do fechamento da véspera:** na B3, a partir das 18h do pregão anterior; em cripto, a
  partir da meia-noite UTC (21h de Brasília), quando o candle diário fecha. Antes disso o dado do
  dia ainda não existe (o Yahoo mostra uma barra parcial durante o pregão);
- **dia sem gravação vira falta e nunca é preenchido:** ao gravar um dia, os dias de negociação
  pulados desde o último (ou desde o início) entram antes como linhas `falta`;
- **o início é fixado uma vez:** o primeiro pregão depois do merge do código (`fixar_inicio`), o
  mesmo para todas as séries.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from trader.agentes.registro import BRASILIA, GENESE, hash_da_linha
from trader.calendario import (
    LEILAO_DE_ABERTURA,
    MERCADOS,
    eh_pregao,
    pregao_anterior,
    proxima_execucao,
    proximo_pregao,
)
from trader.registro import pasta_da_pesquisa_quant

__all__ = ["BRASILIA", "GENESE", "hash_da_linha"]

# fora do Git, como o resto da pesquisa
PASTA_PADRAO = pasta_da_pesquisa_quant() / "papel"
NOME_DO_INICIO = "inicio.json"
CAMPOS_DO_REGISTRO = (
    "serie",
    "tipo",
    "dia",
    "prazo",
    "registrado_em",
    "hash_anterior",
    "hash",
)
GRAVACAO, FALTA = "gravacao", "falta"
MOTIVO_DA_FALTA_PULADA = "não gravado até o prazo"
# o fechamento sai às 17h (leilão de fechamento)
HORA_DEPOIS_DO_FECHAMENTO_DA_B3 = time(18, 0)
NOME_VALIDO = re.compile(r"^[a-z0-9_]+$")


class RegistroAlteradoError(RuntimeError):
    """A cadeia (ou o início) não confere: algo mudou depois de gravado."""


class GravacaoRecusadaError(ValueError):
    """O dia não pode entrar (campo reservado, relógio para trás, dia que não negocia...)."""


class RegravarRecusadoError(GravacaoRecusadaError):
    """O dia já foi gravado (ou já passou como falta): nada se regrava nem se preenche depois."""


class PrazoVencidoError(GravacaoRecusadaError):
    """O pregão em que o sinal valeria já começou: o dia só entra como falta."""


class CedoDemaisError(GravacaoRecusadaError):
    """O fechamento da véspera ainda não saiu: não há dado completo para gravar."""


# --- o relógio de cada mercado -------------------------------------------------------------------


def negocia(dia: date, mercado: str) -> bool:
    _conferir_mercado(mercado)
    return mercado == "cripto" or eh_pregao(dia)


def vespera(dia: date, mercado: str) -> date:
    """O último dia de negociação antes de `dia`: o fechamento de onde sai o sinal que vale em `dia`."""
    _conferir_mercado(mercado)
    return dia - timedelta(days=1) if mercado == "cripto" else pregao_anterior(dia)


def prazo(dia: date, mercado: str) -> datetime:
    """Até quando o sinal que vale em `dia` pode ser gravado (exclusive)."""
    _conferir_mercado(mercado)
    hora = time(0, 0) if mercado == "cripto" else LEILAO_DE_ABERTURA.inicio
    return datetime.combine(dia, hora, BRASILIA)


def abre_em(dia: date, mercado: str) -> datetime:
    """A partir de quando o sinal que vale em `dia` pode ser gravado: o fechamento da véspera saiu."""
    if mercado == "cripto":
        return datetime.combine(dia, time(0, 0), UTC).astimezone(BRASILIA)
    return datetime.combine(
        vespera(dia, mercado), HORA_DEPOIS_DO_FECHAMENTO_DA_B3, BRASILIA
    )


def _conferir_mercado(mercado: str) -> None:
    if mercado not in MERCADOS:
        raise ValueError(f"mercado desconhecido: {mercado!r}; use um de {MERCADOS}")


def _no_relogio(agora: datetime) -> datetime:
    if agora.tzinfo is None:
        raise ValueError("o relógio do papel precisa de fuso horário")
    return agora.astimezone(BRASILIA)


# --- o registro ----------------------------------------------------------------------------------


class RegistroDoPapel:
    def __init__(self, pasta: Path = PASTA_PADRAO) -> None:
        self.pasta = pasta
        self.arquivo_do_inicio = pasta / NOME_DO_INICIO

    # --- o início ---

    def fixar_inicio(self, data_do_merge: date, commit: str, agora: datetime) -> dict:
        """Grava, uma única vez, o início do papel: o primeiro pregão depois do merge."""
        if self.arquivo_do_inicio.exists():
            raise RegravarRecusadoError(
                f"o início do papel já está fixado em {self.inicio()}"
            )
        conteudo = {
            "inicio": proximo_pregao(data_do_merge).isoformat(),
            "merge": data_do_merge.isoformat(),
            "commit": commit,
            "registrado_em": _no_relogio(agora).isoformat(),
        }
        conteudo["hash"] = hash_da_linha(conteudo)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo_do_inicio.write_text(
            json.dumps(conteudo, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return conteudo

    def inicio(self) -> date | None:
        if not self.arquivo_do_inicio.exists():
            return None
        conteudo = json.loads(self.arquivo_do_inicio.read_text(encoding="utf-8"))
        if hash_da_linha(conteudo) != conteudo.get("hash"):
            raise RegistroAlteradoError(
                "o arquivo do início do papel mudou depois de gravado"
            )
        return date.fromisoformat(conteudo["inicio"])

    # --- leitura ---

    def arquivo(self, serie: str) -> Path:
        if not NOME_VALIDO.match(serie):
            raise ValueError(
                f"nome de série inválido: {serie!r} (só minúsculas, números e _)"
            )
        return self.pasta / f"{serie}.jsonl"

    def series(self) -> list[str]:
        return sorted(a.stem for a in self.pasta.glob("*.jsonl"))

    def linhas(self, serie: str) -> list[dict]:
        arquivo = self.arquivo(serie)
        if not arquivo.exists():
            return []
        texto = arquivo.read_text(encoding="utf-8")
        return [json.loads(linha) for linha in texto.splitlines() if linha.strip()]

    def ponta(self, serie: str) -> str:
        linhas = self.linhas(serie)
        return linhas[-1]["hash"] if linhas else GENESE

    def proximo_dia(self, serie: str, mercado: str) -> date | None:
        """O próximo dia sem linha: o seguinte ao último gravado, ou o início do papel."""
        linhas = self.linhas(serie)
        if linhas:
            return proxima_execucao(date.fromisoformat(linhas[-1]["dia"]), mercado)
        return self.inicio()

    def verificar(self, serie: str) -> None:
        """Recalcula a cadeia inteira da série; falha dizendo onde não confere."""
        anterior = GENESE
        ultimo_dia = ""
        for numero, linha in enumerate(self.linhas(serie), start=1):
            if linha.get("hash_anterior") != anterior:
                raise RegistroAlteradoError(
                    f"{serie}: a cadeia quebra na linha {numero}: falta ou sobra uma linha antes dela"
                )
            if hash_da_linha(linha) != linha.get("hash"):
                raise RegistroAlteradoError(
                    f"{serie}: a linha {numero} ({linha.get('dia')}) mudou depois de gravada"
                )
            if linha.get("serie") != serie or linha.get("dia", "") <= ultimo_dia:
                raise RegistroAlteradoError(
                    f"{serie}: a linha {numero} ({linha.get('dia')}) está fora de ordem ou é de outra série"
                )
            anterior, ultimo_dia = linha["hash"], linha["dia"]

    # --- escrita ---

    def gravar(
        self, serie: str, mercado: str, dia: date, foto: dict, agora: datetime
    ) -> dict:
        """Grava a foto do sinal que vale em `dia` e devolve a linha; os dias pulados viram falta."""
        reservados = sorted(set(foto) & set(CAMPOS_DO_REGISTRO))
        if reservados:
            raise GravacaoRecusadaError(
                f"o registro é quem põe {', '.join(reservados)} (a data vem do relógio)"
            )
        if foto.get("fechamento") != vespera(dia, mercado).isoformat():
            raise GravacaoRecusadaError(
                f"o sinal que vale em {dia} sai do fechamento da véspera "
                f"({vespera(dia, mercado)}), não de {foto.get('fechamento')}"
            )
        agora = self._conferir_dia(serie, mercado, dia, agora)
        if agora >= prazo(dia, mercado):
            raise PrazoVencidoError(
                f"{serie}: o prazo de {dia} era {prazo(dia, mercado).isoformat()}; o dia só entra como falta"
            )
        if agora < abre_em(dia, mercado):
            raise CedoDemaisError(
                f"{serie}: o fechamento de {vespera(dia, mercado)} só está completo a partir de "
                f"{abre_em(dia, mercado).isoformat()}"
            )
        self._faltas_ate(serie, mercado, dia, agora)
        return self._acrescentar(serie, mercado, dia, GRAVACAO, foto, agora)

    def registrar_falta(
        self, serie: str, mercado: str, dia: date, motivo: str, agora: datetime
    ) -> dict:
        """Registra que `dia` passou sem gravação (só depois do prazo); nunca é preenchido depois."""
        agora = self._conferir_dia(serie, mercado, dia, agora)
        if agora < prazo(dia, mercado):
            raise GravacaoRecusadaError(
                f"{serie}: {dia} ainda está no prazo ({prazo(dia, mercado).isoformat()}); grave o dia"
            )
        self._faltas_ate(serie, mercado, dia, agora)
        return self._acrescentar(serie, mercado, dia, FALTA, {"motivo": motivo}, agora)

    def _conferir_dia(
        self, serie: str, mercado: str, dia: date, agora: datetime
    ) -> datetime:
        agora = _no_relogio(agora)
        if not negocia(dia, mercado):
            raise GravacaoRecusadaError(f"{dia} não negocia em {mercado}")
        inicio = self.inicio()
        if inicio is not None and dia < inicio:
            raise GravacaoRecusadaError(f"{dia} é antes do início do papel ({inicio})")
        self.verificar(serie)
        linhas = self.linhas(serie)
        if linhas:
            ultima = linhas[-1]
            if dia.isoformat() <= ultima["dia"]:
                raise RegravarRecusadoError(
                    f"{serie}: {dia} já gravado ou anterior ao último dia ({ultima['dia']}, {ultima['tipo']}): "
                    "nada se regrava"
                )
            if agora < datetime.fromisoformat(ultima["registrado_em"]):
                raise GravacaoRecusadaError(
                    f"relógio ({agora.isoformat()}) anterior à última linha ({ultima['registrado_em']})"
                )
        return agora

    def _faltas_ate(self, serie: str, mercado: str, dia: date, agora: datetime) -> None:
        pulado = self.proximo_dia(serie, mercado)
        while pulado is not None and pulado < dia:
            self._acrescentar(
                serie, mercado, pulado, FALTA, {"motivo": MOTIVO_DA_FALTA_PULADA}, agora
            )
            pulado = proxima_execucao(pulado, mercado)

    def _acrescentar(
        self,
        serie: str,
        mercado: str,
        dia: date,
        tipo: str,
        conteudo: dict,
        agora: datetime,
    ) -> dict:
        linha = {
            **conteudo,
            "serie": serie,
            "tipo": tipo,
            "dia": dia.isoformat(),
            "prazo": prazo(dia, mercado).isoformat(),
            "registrado_em": agora.isoformat(),
            "hash_anterior": self.ponta(serie),
        }
        linha["hash"] = hash_da_linha(linha)
        texto = json.dumps(linha, ensure_ascii=False, sort_keys=True, allow_nan=False)
        self.pasta.mkdir(parents=True, exist_ok=True)
        with self.arquivo(serie).open("a", encoding="utf-8", newline="\n") as saida:
            saida.write(texto + "\n")
        return linha
