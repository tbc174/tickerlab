// Calculadora de juros simples e compostos (conta em contas/juros.ts, a mesma do Python).
import { useState } from "react";
import { Alternativas, CampoDeNumero, Escolha, Resultado } from "./campos";
import { type Linha, PRAZO_MAXIMO, type Unidade, evolucao, montante, taxaPorMes } from "./contas/juros";
import { formatarNumero, formatarReais, lerNumero } from "./numeros";

type Tipo = "composto" | "simples";
type UnidadeDoPrazo = "meses" | "anos";

export const EXEMPLO_DE_JUROS = {
  capital: "10.000",
  taxa: "10",
  unidadeDaTaxa: "ano" as Unidade,
  prazo: "10",
  unidadeDoPrazo: "anos" as UnidadeDoPrazo,
  tipo: "composto" as Tipo,
};

interface Conta {
  linhas: Linha[];
  final: number;
  simples: number;
}

/** Lê os campos e faz a conta; devolve a mensagem para a pessoa quando algo não fecha. */
export function calcularJuros(campos: typeof EXEMPLO_DE_JUROS): Conta | string {
  const capital = lerNumero(campos.capital);
  const taxa = lerNumero(campos.taxa);
  const prazo = lerNumero(campos.prazo);
  if (capital === null || taxa === null || prazo === null) {
    return "Preencha o valor, a taxa e o prazo com números (por exemplo, 1.000,50).";
  }
  const meses = campos.unidadeDoPrazo === "anos" ? prazo * 12 : prazo;
  if (!Number.isInteger(meses)) return "Use um prazo em meses inteiros.";
  if (meses > PRAZO_MAXIMO) return `O prazo vai até ${PRAZO_MAXIMO / 12} anos.`;
  try {
    const porMes = taxaPorMes(taxa / 100, campos.unidadeDaTaxa);
    const composto = campos.tipo === "composto";
    return {
      linhas: evolucao(capital, porMes, meses, composto),
      final: montante(capital, porMes, meses, composto),
      simples: montante(capital, porMes, meses, false),
    };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

/** Até 2 anos, mês a mês; depois, o fim de cada ano (e o último mês, se não fechar um ano). */
function linhasDaTabela(linhas: Linha[]): Linha[] {
  if (linhas.length <= 25) return linhas.slice(1);
  return linhas.filter((l, i) => l.periodo > 0 && (l.periodo % 12 === 0 || i === linhas.length - 1));
}

export function CalculadoraDeJuros() {
  const [campos, setCampos] = useState(EXEMPLO_DE_JUROS);
  const mudar = <K extends keyof typeof campos>(chave: K) => (valor: (typeof campos)[K]) =>
    setCampos((antes) => ({ ...antes, [chave]: valor }));
  const conta = calcularJuros(campos);
  const erro = typeof conta === "string" ? conta : null;
  const capital = lerNumero(campos.capital) ?? 0;

  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor aplicado" antes="R$" valor={campos.capital} aoMudar={mudar("capital")} />
        <CampoDeNumero
          rotulo="Taxa de juros"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
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
        <CampoDeNumero
          rotulo="Prazo"
          valor={campos.prazo}
          aoMudar={mudar("prazo")}
          depois={
            <Escolha
              rotulo="Unidade do prazo"
              valor={campos.unidadeDoPrazo}
              opcoes={[
                ["meses", "meses"],
                ["anos", "anos"],
              ]}
              aoMudar={mudar("unidadeDoPrazo")}
            />
          }
        />
        <Alternativas
          rotulo="Tipo de juros"
          valor={campos.tipo}
          opcoes={[
            ["composto", "Compostos (juro sobre juro)"],
            ["simples", "Simples"],
          ]}
          aoMudar={mudar("tipo")}
        />
      </form>
      <Resultado rotulo="Valor no fim do prazo" principal={erro ? "" : formatarReais((conta as Conta).final)} erro={erro}>
        {erro ? null : (
          <>
            <dl className="ferramenta-numeros">
              <div>
                <dt>Juros ganhos</dt>
                <dd>{formatarReais((conta as Conta).final - capital)}</dd>
              </div>
              {campos.tipo === "composto" ? (
                <div>
                  <dt>Com juros simples daria</dt>
                  <dd>{formatarReais((conta as Conta).simples)}</dd>
                </div>
              ) : null}
            </dl>
            <details className="ferramenta-tabela">
              <summary>Ver a evolução</summary>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Mês</th>
                    <th scope="col">Juros no mês</th>
                    <th scope="col">Juros acumulados</th>
                    <th scope="col">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {linhasDaTabela((conta as Conta).linhas).map((l) => (
                    <tr key={l.periodo}>
                      <td>{formatarNumero(l.periodo)}</td>
                      <td>{formatarReais(l.juros_no_periodo)}</td>
                      <td>{formatarReais(l.juros_acumulados)}</td>
                      <td>{formatarReais(l.montante)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        )}
      </Resultado>
    </div>
  );
}
