// DARF de ações (contas/darf.ts, a mesma conta do Python): um mês por vez, com o que vem dos meses
// anteriores e o que passa para o seguinte.
import { useEffect, useState } from "react";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { type Apuracao, CODIGO_DO_DARF, DARF_MINIMO, apurarMes, vencimento } from "./contas/darf";
import { formatarReais, lerNumero } from "./numeros";

const NOMES_DOS_MESES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

// o exemplo do HTML pronto (o build não pode depender do dia em que roda); no navegador, a
// calculadora troca o mês e o ano pelos de hoje
export const EXEMPLO_DO_DARF = {
  mes: "9",
  ano: "2026",
  vendas: "30.000",
  resultadoComum: "3.000",
  resultadoDayTrade: "0",
  irrf: "1,50",
  prejuizoComum: "0",
  prejuizoDayTrade: "0",
  irrfAnterior: "0",
  acumulado: "0",
};

type Campos = typeof EXEMPLO_DO_DARF;

/** Lê os campos e apura o mês; devolve a mensagem quando algo não fecha. */
export function apurar(campos: Campos): Apuracao | string {
  const numeros = [
    campos.vendas, campos.resultadoComum, campos.resultadoDayTrade, campos.irrf,
    campos.prejuizoComum, campos.prejuizoDayTrade, campos.irrfAnterior, campos.acumulado,
  ].map((texto) => (texto.trim() === "" ? 0 : lerNumero(texto)));
  if (numeros.some((n) => n === null)) return "Preencha os campos com números (por exemplo, 1.000,50).";
  const [vendas, comum, dayTrade, irrf, prejComum, prejDt, irrfAnterior, acumulado] = numeros as number[];
  try {
    return apurarMes(
      {
        vendas_comuns: vendas,
        resultado_comum: comum,
        resultado_day_trade: dayTrade,
        irrf_comum: irrf,
      },
      {
        prejuizo_comum: Math.abs(prejComum),
        prejuizo_day_trade: Math.abs(prejDt),
        irrf_a_compensar: irrfAnterior,
        imposto_abaixo_do_minimo: acumulado,
      },
    );
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

/** Por que não há DARF neste mês, ou o valor a pagar. */
export function principal(a: Apuracao): [string, string] {
  if (a.darf > 0) return ["DARF a pagar", formatarReais(a.darf)];
  if (a.isento) return ["Nada a pagar", "Isento"];
  if (a.saldos_seguintes.imposto_abaixo_do_minimo > 0) return ["Nada a pagar neste mês", "Abaixo de R$ 10"];
  return ["Nada a pagar", "Sem imposto"];
}

export function CalculadoraDeDarf() {
  const [campos, setCampos] = useState(EXEMPLO_DO_DARF);
  useEffect(() => {
    const hoje = new Date();
    // o mês que se apura é o anterior ao de hoje
    const anterior = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
    setCampos((antes) => ({ ...antes, mes: String(anterior.getMonth() + 1), ano: String(anterior.getFullYear()) }));
  }, []);
  const mudar = (chave: keyof Campos) => (valor: string) => setCampos((antes) => ({ ...antes, [chave]: valor }));
  const conta = apurar(campos);
  const erro = typeof conta === "string" ? conta : null;
  const a = typeof conta === "string" ? null : conta;
  const [rotulo, valor] = a ? principal(a) : ["", ""];
  const ano = Number(campos.ano);
  const prazo = Number.isInteger(ano) && ano > 2000 ? vencimento(ano, Number(campos.mes)) : "o último dia útil do mês seguinte";
  const prejuizo = "Use o sinal de menos para prejuízo (−500). Já com corretagem e taxas descontadas.";
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Mês das operações</span>
          <div className="ferramenta-entrada">
            <Escolha
              rotulo="Mês das operações"
              valor={campos.mes}
              opcoes={NOMES_DOS_MESES.map((nome, i) => [String(i + 1), nome])}
              aoMudar={mudar("mes")}
            />
            <input aria-label="Ano das operações" type="text" inputMode="numeric" value={campos.ano} onChange={(e) => mudar("ano")(e.target.value)} />
          </div>
        </div>
        <CampoDeNumero rotulo="Total vendido em ações (sem day trade)" antes="R$" valor={campos.vendas} aoMudar={mudar("vendas")} />
        <CampoDeNumero rotulo="Resultado das operações comuns" antes="R$" valor={campos.resultadoComum} aoMudar={mudar("resultadoComum")} dica={prejuizo} />
        <CampoDeNumero rotulo="Resultado do day trade" antes="R$" valor={campos.resultadoDayTrade} aoMudar={mudar("resultadoDayTrade")} />
        <CampoDeNumero
          rotulo="IR retido na fonte no mês"
          antes="R$"
          valor={campos.irrf}
          aoMudar={mudar("irrf")}
          dica="O “dedo-duro” das notas de corretagem (0,005% das vendas e 1% do lucro do day trade)."
        />
        <details className="ferramenta-anteriores">
          <summary>Vem dos meses anteriores?</summary>
          <CampoDeNumero rotulo="Prejuízo a compensar, operações comuns" antes="R$" valor={campos.prejuizoComum} aoMudar={mudar("prejuizoComum")} />
          <CampoDeNumero rotulo="Prejuízo a compensar, day trade" antes="R$" valor={campos.prejuizoDayTrade} aoMudar={mudar("prejuizoDayTrade")} />
          <CampoDeNumero rotulo="IR retido que sobrou" antes="R$" valor={campos.irrfAnterior} aoMudar={mudar("irrfAnterior")} />
          <CampoDeNumero rotulo="Imposto abaixo de R$ 10 ainda não pago" antes="R$" valor={campos.acumulado} aoMudar={mudar("acumulado")} />
        </details>
      </form>
      <Resultado rotulo={rotulo} principal={valor} erro={erro}>
        {a ? (
          <>
            {a.darf > 0 ? (
              <p>
                Código <strong>{CODIGO_DO_DARF}</strong>, até o {prazo}.
              </p>
            ) : null}
            {a.isento ? <p>Vendas comuns de até R$ 20.000 no mês: o lucro dessas operações é isento.</p> : null}
            {a.darf === 0 && a.saldos_seguintes.imposto_abaixo_do_minimo > 0 ? (
              <p>DARF abaixo de R$ {DARF_MINIMO} não se paga: o valor passa para o mês seguinte.</p>
            ) : null}
            <dl className="ferramenta-numeros">
              <div>
                <dt>Imposto das operações comuns (15%)</dt>
                <dd>{formatarReais(a.imposto_comum)}</dd>
              </div>
              <div>
                <dt>Imposto do day trade (20%)</dt>
                <dd>{formatarReais(a.imposto_day_trade)}</dd>
              </div>
              <div>
                <dt>IR retido abatido</dt>
                <dd>{formatarReais(a.irrf_usado)}</dd>
              </div>
            </dl>
            <p className="olho ferramenta-depois">Para o mês seguinte</p>
            <dl className="ferramenta-numeros">
              <div>
                <dt>Prejuízo a compensar, comuns</dt>
                <dd>{formatarReais(a.saldos_seguintes.prejuizo_comum)}</dd>
              </div>
              <div>
                <dt>Prejuízo a compensar, day trade</dt>
                <dd>{formatarReais(a.saldos_seguintes.prejuizo_day_trade)}</dd>
              </div>
              <div>
                <dt>IR retido que sobrou</dt>
                <dd>{formatarReais(a.saldos_seguintes.irrf_a_compensar)}</dd>
              </div>
              <div>
                <dt>Imposto abaixo de R$ 10</dt>
                <dd>{formatarReais(a.saldos_seguintes.imposto_abaixo_do_minimo)}</dd>
              </div>
            </dl>
          </>
        ) : null}
      </Resultado>
    </div>
  );
}
