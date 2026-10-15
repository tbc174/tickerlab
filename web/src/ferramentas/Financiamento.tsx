// Financiamento SAC × Price (contas/financiamento.ts, a mesma conta do Python): os dois sistemas lado a
// lado, quanto a Price paga a mais de juros, o gráfico das parcelas, uma tabela por ano e uma
// amortização extra opcional (reduzindo o prazo ou a parcela).
import { Compartilhar } from "./Compartilhar";
import { Alternativas, CampoComDeslizante, CampoDeNumero, Escolha, Resultado } from "./campos";
import { type Linha, PRAZO_MAXIMO, tabela } from "./contas/financiamento";
import { type Unidade, taxaPorMes } from "./contas/juros";
import { useCamposNoEndereco } from "./endereco";
import { formatarNumero, formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

export const EXEMPLO_DO_FINANCIAMENTO = {
  valor: "300.000",
  taxa: "11",
  unidadeDaTaxa: "ano" as Unidade,
  anos: "30",
  extra: "0",
  mesDaExtra: "12",
  modo: "prazo" as "prazo" | "parcela",
};
const OPCOES = { unidadeDaTaxa: ["mes", "ano"], modo: ["prazo", "parcela"] } as const;
type Campos = typeof EXEMPLO_DO_FINANCIAMENTO;

export interface Comparacao {
  sac: Linha[];
  price: Linha[];
}

/** Os dois sistemas pelos campos, ou a mensagem quando algo não fecha. */
export function calcularFinanciamento(campos: Campos): Comparacao | string {
  const [valor, taxa, anos, extra, mesDaExtra] = [campos.valor, campos.taxa, campos.anos, campos.extra, campos.mesDaExtra].map(
    (t) => (t.trim() === "" ? 0 : lerNumero(t)),
  );
  if ([valor, taxa, anos, extra, mesDaExtra].some((n) => n === null)) {
    return "Preencha os campos com números (por exemplo, 300.000).";
  }
  const meses = Math.round((anos as number) * 12);
  if (meses > PRAZO_MAXIMO) return `O prazo vai até ${PRAZO_MAXIMO / 12} anos.`;
  try {
    const porMes = taxaPorMes((taxa as number) / 100, campos.unidadeDaTaxa);
    const linhas = (sistema: string) =>
      tabela(sistema, valor as number, porMes, meses, Math.round(mesDaExtra as number), extra as number, campos.modo);
    return { sac: linhas("sac"), price: linhas("price") };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

const somar = (linhas: Linha[], campo: "juros" | "parcela" | "extra") => linhas.reduce((s, l) => s + l[campo], 0);

/** O saldo no fim de cada ano (12, 24...) e no último mês. */
function saldosPorAno(linhas: Linha[]): Map<number, number> {
  return new Map(linhas.filter((l, i) => l.mes % 12 === 0 || i === linhas.length - 1).map((l) => [Math.ceil(l.mes / 12), l.saldo]));
}

export function Financiamento() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DO_FINANCIAMENTO, OPCOES);
  const conta = calcularFinanciamento(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  const diferenca = r ? somar(r.price, "juros") - somar(r.sac, "juros") : 0;
  const maisLonga = r ? Math.max(r.sac.length, r.price.length) : 0;
  const meses = Array.from({ length: maisLonga }, (_, i) => i + 1);
  const parcelas = (linhas: Linha[]) => meses.map((m) => linhas[m - 1]?.parcela ?? 0);
  const anos = r ? Math.ceil(maisLonga / 12) : 0;
  const saldosSac = r ? saldosPorAno(r.sac) : new Map<number, number>();
  const saldosPrice = r ? saldosPorAno(r.price) : new Map<number, number>();
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante rotulo="Valor financiado" antes="R$" valor={campos.valor} aoMudar={mudar("valor")} min={10000} max={2000000} passo={10000} />
        <CampoComDeslizante
          rotulo="Taxa de juros"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          min={0}
          max={campos.unidadeDaTaxa === "ano" ? 20 : 2}
          passo={campos.unidadeDaTaxa === "ano" ? 0.25 : 0.05}
          depois={
            <>
              <span aria-hidden="true">%</span>
              <Escolha
                rotulo="Período da taxa"
                valor={campos.unidadeDaTaxa}
                opcoes={[
                  ["mes", "ao mês"],
                  ["ano", "ao ano"],
                ]}
                aoMudar={mudar("unidadeDaTaxa")}
              />
            </>
          }
        />
        <CampoComDeslizante rotulo="Prazo" valor={campos.anos} aoMudar={mudar("anos")} min={1} max={35} passo={1} depois={<span>anos</span>} />
        <fieldset className="ferramenta-cenario-b">
          <legend>Amortização extra (opcional)</legend>
          <CampoDeNumero rotulo="Amortização extra" antes="R$" valor={campos.extra} aoMudar={mudar("extra")} />
          <CampoDeNumero rotulo="No mês" valor={campos.mesDaExtra} aoMudar={mudar("mesDaExtra")} />
          <Alternativas
            rotulo="Para"
            valor={campos.modo}
            opcoes={[
              ["prazo", "Reduzir o prazo"],
              ["parcela", "Reduzir a parcela"],
            ]}
            aoMudar={mudar("modo")}
          />
        </fieldset>
      </form>
      <Resultado rotulo="A Price paga a mais de juros que o SAC" principal={r ? formatarReais(diferenca) : ""} erro={erro}>
        {r ? (
          <table className="ferramenta-comparacao">
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col">SAC</th>
                <th scope="col">Price</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["Primeira parcela", (l: Linha[]) => formatarReais(l[0].parcela)],
                  ["Última parcela", (l: Linha[]) => formatarReais(l[l.length - 1].parcela)],
                  ["Total de juros", (l: Linha[]) => formatarReais(somar(l, "juros"))],
                  ["Total pago", (l: Linha[]) => formatarReais(somar(l, "parcela") + somar(l, "extra"))],
                  ["Prazo", (l: Linha[]) => `${formatarNumero(l.length)} meses`],
                ] as [string, (l: Linha[]) => string][]
              ).map(([nome, valor]) => (
                <tr key={nome}>
                  <th scope="row">{nome}</th>
                  <td>{valor(r.sac)}</td>
                  <td>{valor(r.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Resultado>
      {r ? (
        <div className="ferramenta-largo">
          <GraficoDoTempo
            titulo="A parcela de cada mês, nos dois sistemas"
            meses={meses}
            series={[
              { nome: "SAC", cor: SERIES[0], valores: parcelas(r.sac) },
              { nome: "Price", cor: SERIES[1], valores: parcelas(r.price) },
            ]}
            zeroNaBase
            formatarValor={formatarReais}
            formatarEixo={formatarReaisCurto}
          />
          <details className="ferramenta-tabela">
            <summary>Ver o saldo devedor ano a ano</summary>
            <table>
              <thead>
                <tr>
                  <th scope="col">Ano</th>
                  <th scope="col">Saldo no SAC</th>
                  <th scope="col">Saldo na Price</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: anos }, (_, i) => i + 1).map((ano) => (
                  <tr key={ano}>
                    <td>{ano}</td>
                    <td>{formatarReais(saldosSac.get(ano) ?? 0)}</td>
                    <td>{formatarReais(saldosPrice.get(ano) ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <Compartilhar
            resultado={`Financiar ${formatarReais(lerNumero(campos.valor) ?? 0)} em ${campos.anos} anos: a Price paga ${formatarReais(diferenca)} a mais de juros que o SAC`}
          />
        </div>
      ) : null}
    </div>
  );
}
