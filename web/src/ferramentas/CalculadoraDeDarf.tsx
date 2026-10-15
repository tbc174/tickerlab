// DARF de ações (contas/darf.ts, a mesma conta do Python): um mês por vez, com o que vem dos meses
// anteriores e o que passa para o seguinte, ou (v2) o ano inteiro numa grade de 12 meses, com o
// prejuízo e o imposto abaixo de R$ 10 passando de um mês para o outro e o resumo do ano.
import { useEffect, useState } from "react";
import { Compartilhar } from "./Compartilhar";
import { Alternativas, CampoDeNumero, Escolha, Resultado } from "./campos";
import { type Apuracao, CODIGO_DO_DARF, DARF_MINIMO, apurarMes, apurarMeses, vencimento } from "./contas/darf";
import { useCamposNoEndereco } from "./endereco";
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

// --- o ano inteiro (v2) --------------------------------------------------------------------------
const MESES_DO_ANO = Array.from({ length: 12 }, (_, i) => i + 1);
// as colunas de entrada de cada mês: [prefixo da chave no endereço, rótulo]
const COLUNAS_DO_ANO: [string, string][] = [
  ["v", "Vendas"],
  ["c", "Resultado comum"],
  ["d", "Day trade"],
  ["i", "IR retido"],
];

// um ano de exemplo: lucro em janeiro, prejuízo em fevereiro, lucro isento em março (vendas abaixo de
// R$ 20 mil, que não gasta o prejuízo), lucro em abril (compensa o prejuízo) e um day trade em maio
const MESES_DE_EXEMPLO: Record<number, [string, string, string, string]> = {
  1: ["30.000", "3.000", "0", "1,50"],
  2: ["25.000", "-2.000", "0", "1,25"],
  3: ["15.000", "1.500", "0", "0,75"],
  4: ["40.000", "2.500", "0", "2"],
  5: ["0", "0", "800", "8"],
};

export const EXEMPLO_DO_ANO: Record<string, string> = {
  ano: "2025",
  pc0: "0", // prejuízo comum que vem do ano anterior
  pd0: "0", // prejuízo de day trade que vem do ano anterior
  ...Object.fromEntries(
    MESES_DO_ANO.flatMap((m) => COLUNAS_DO_ANO.map(([letra], k) => [`${letra}${m}`, MESES_DE_EXEMPLO[m]?.[k] ?? "0"])),
  ),
};

export interface AnoApurado {
  meses: Apuracao[];
  total: number;
  prejuizoQueSobra: { comum: number; dayTrade: number };
}

const numeroOuZero = (texto: string | undefined) => (texto === undefined || texto.trim() === "" ? 0 : lerNumero(texto));

/** Os 12 meses apurados em sequência (contas/darf.ts, apurarMeses), o total e o que sobra. */
export function apurarOAno(campos: Record<string, string>): AnoApurado | string {
  const meses = MESES_DO_ANO.map((m) => COLUNAS_DO_ANO.map(([letra]) => numeroOuZero(campos[`${letra}${m}`])));
  const anteriores = [numeroOuZero(campos.pc0), numeroOuZero(campos.pd0)];
  if (meses.flat().some((n) => n === null) || anteriores.some((n) => n === null)) {
    return "Preencha os meses com números (por exemplo, 1.000,50; prejuízo com o sinal de menos).";
  }
  try {
    const apuracoes = apurarMeses(
      meses.map(([vendas, comum, dayTrade, irrf]) => ({
        vendas_comuns: vendas as number,
        resultado_comum: comum as number,
        resultado_day_trade: dayTrade as number,
        irrf_comum: irrf as number,
      })),
      { prejuizo_comum: Math.abs(anteriores[0] as number), prejuizo_day_trade: Math.abs(anteriores[1] as number) },
    );
    const ultimo = apuracoes[apuracoes.length - 1].saldos_seguintes;
    return {
      meses: apuracoes,
      total: apuracoes.reduce((soma, a) => soma + a.darf, 0),
      prejuizoQueSobra: { comum: ultimo.prejuizo_comum, dayTrade: ultimo.prejuizo_day_trade },
    };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

function DarfDoAno() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DO_ANO);
  const conta = apurarOAno(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  const ano = Number(campos.ano);
  const anoValido = Number.isInteger(ano) && ano > 2000;
  const pagos = r ? r.meses.filter((m) => m.darf > 0).length : 0;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos ferramenta-largo darf-do-ano" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Ano das operações" valor={campos.ano} aoMudar={mudar("ano")} />
        <div className="ferramenta-rolagem">
          <table>
            <thead>
              <tr>
                <th scope="col">Mês</th>
                {COLUNAS_DO_ANO.map(([letra, nome]) => (
                  <th scope="col" key={letra}>
                    {nome}
                  </th>
                ))}
                <th scope="col">DARF</th>
                <th scope="col">Prejuízo que fica (comum / day trade)</th>
              </tr>
            </thead>
            <tbody>
              {MESES_DO_ANO.map((m) => {
                const a = r?.meses[m - 1];
                return (
                  <tr key={m}>
                    <th scope="row">{NOMES_DOS_MESES[m - 1]}</th>
                    {COLUNAS_DO_ANO.map(([letra, nome]) => (
                      <td key={letra}>
                        <input
                          type="text"
                          inputMode="decimal"
                          aria-label={`${nome} em ${NOMES_DOS_MESES[m - 1]}`}
                          value={campos[`${letra}${m}`]}
                          onChange={(evento) => mudar(`${letra}${m}`)(evento.target.value)}
                        />
                      </td>
                    ))}
                    <td>{a ? (a.darf > 0 ? formatarReais(a.darf) : a.isento ? "isento" : "—") : ""}</td>
                    <td>
                      {a
                        ? `${formatarReais(a.saldos_seguintes.prejuizo_comum)} / ${formatarReais(a.saldos_seguintes.prejuizo_day_trade)}`
                        : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <details className="ferramenta-anteriores">
          <summary>Prejuízo que vem do ano anterior?</summary>
          <CampoDeNumero rotulo="Prejuízo a compensar, operações comuns" antes="R$" valor={campos.pc0} aoMudar={mudar("pc0")} />
          <CampoDeNumero rotulo="Prejuízo a compensar, day trade" antes="R$" valor={campos.pd0} aoMudar={mudar("pd0")} />
        </details>
      </form>
      <Resultado rotulo={anoValido ? `Imposto sobre ações em ${ano}` : "Imposto do ano"} principal={r ? formatarReais(r.total) : ""} erro={erro}>
        {r ? (
          <>
            <p>
              {pagos ? `Em ${pagos} ${pagos === 1 ? "DARF" : "DARFs"}, código ${CODIGO_DO_DARF}, cada um até o último dia útil do mês seguinte ao das operações.` : "Nenhum DARF a pagar no ano."}
            </p>
            <dl className="ferramenta-numeros">
              <div>
                <dt>Prejuízo que passa para {anoValido ? ano + 1 : "o ano seguinte"}, comum</dt>
                <dd>{formatarReais(r.prejuizoQueSobra.comum)}</dd>
              </div>
              <div>
                <dt>Prejuízo que passa para {anoValido ? ano + 1 : "o ano seguinte"}, day trade</dt>
                <dd>{formatarReais(r.prejuizoQueSobra.dayTrade)}</dd>
              </div>
            </dl>
            <Compartilhar
              resultado={`Imposto sobre ações em ${anoValido ? ano : "?"}: ${formatarReais(r.total)} em ${pagos} DARFs; prejuízo que passa para o ano seguinte: ${formatarReais(r.prejuizoQueSobra.comum)} (comum) e ${formatarReais(r.prejuizoQueSobra.dayTrade)} (day trade)`}
            />
          </>
        ) : null}
      </Resultado>
    </div>
  );
}

/** Um mês ou o ano inteiro (a escolha vai no endereço). */
export function CalculadoraDeDarf() {
  const [escolha, mudarEscolha] = useCamposNoEndereco({ modo: "mes" as "mes" | "ano" }, { modo: ["mes", "ano"] });
  return (
    <>
      <Alternativas
        rotulo="Calcular"
        valor={escolha.modo}
        opcoes={[
          ["mes", "Um mês"],
          ["ano", "O ano inteiro"],
        ]}
        aoMudar={mudarEscolha("modo")}
      />
      {escolha.modo === "ano" ? <DarfDoAno /> : <DarfDoMes />}
    </>
  );
}

function DarfDoMes() {
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
