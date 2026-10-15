// Calculadora de juros simples e compostos (conta em contas/juros.ts, a mesma do Python), v2: gráfico
// do que foi aplicado e dos juros, cenário B para comparar, o valor em reais de hoje e depois do IR,
// deslizantes e a simulação guardada no endereço.
import { Compartilhar } from "./Compartilhar";
import { atalhosDeInflacao, atalhosDeJuros } from "./atalhos";
import { Alternativas, CampoComDeslizante, CampoDeNumero, Escolha, Resultado } from "./campos";
import {
  type Linha,
  PRAZO_MAXIMO,
  type Unidade,
  emReaisDeHoje,
  evolucao,
  liquidoDeIr,
  montante,
  taxaPorMes,
} from "./contas/juros";
import { useDadosOpcionais } from "./dados";
import { useCamposNoEndereco } from "./endereco";
import { formatarNumero, formatarPorcentagem, formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

type Tipo = "composto" | "simples";
type UnidadeDoPrazo = "meses" | "anos";

export const EXEMPLO_DE_JUROS = {
  capital: "10.000",
  taxa: "10",
  unidadeDaTaxa: "ano" as Unidade,
  prazo: "10",
  unidadeDoPrazo: "anos" as UnidadeDoPrazo,
  tipo: "composto" as Tipo,
  inflacao: "4", // % ao ano, para o "em reais de hoje"
  comparar: "nao" as "nao" | "sim",
  capitalB: "10.000",
  taxaB: "12",
};

const OPCOES = {
  unidadeDaTaxa: ["mes", "ano"],
  unidadeDoPrazo: ["meses", "anos"],
  tipo: ["composto", "simples"],
  comparar: ["nao", "sim"],
} as const;

type Campos = typeof EXEMPLO_DE_JUROS;

interface Conta {
  linhas: Linha[];
  final: number;
  simples: number;
  meses: number;
}

/** Lê os campos e faz a conta; devolve a mensagem para a pessoa quando algo não fecha. */
export function calcularJuros(campos: Pick<Campos, "capital" | "taxa" | "unidadeDaTaxa" | "prazo" | "unidadeDoPrazo" | "tipo">): Conta | string {
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
      meses,
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

/** Os pontos do gráfico: todo mês até 10 anos; depois, um por ano (e o último mês). */
function pontosDoGrafico(linhas: Linha[]): Linha[] {
  if (linhas.length <= 121) return linhas;
  return linhas.filter((l, i) => l.periodo % 12 === 0 || i === linhas.length - 1);
}

function prazoPorExtenso(campos: Campos): string {
  const unidade = campos.unidadeDoPrazo === "anos" ? (campos.prazo === "1" ? "ano" : "anos") : campos.prazo === "1" ? "mês" : "meses";
  return `${campos.prazo} ${unidade}`;
}

export function CalculadoraDeJuros() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DE_JUROS, OPCOES);
  const dados = useDadosOpcionais();
  const hoje = new Date();
  const conta = calcularJuros(campos);
  const erro = typeof conta === "string" ? conta : null;
  const capital = lerNumero(campos.capital) ?? 0;
  const inflacao = lerNumero(campos.inflacao);
  const comparar = campos.comparar === "sim";
  const contaB = comparar ? calcularJuros({ ...campos, capital: campos.capitalB, taxa: campos.taxaB }) : null;
  const erroB = typeof contaB === "string" ? contaB : null;
  const unidadeDaTaxa = campos.unidadeDaTaxa === "ano" ? "ao ano" : "ao mês";
  const escolhaDaUnidade = (
    <Escolha
      rotulo="Período da taxa"
      valor={campos.unidadeDaTaxa}
      opcoes={[
        ["mes", "ao mês"],
        ["ano", "ao ano"],
      ]}
      aoMudar={mudar("unidadeDaTaxa")}
    />
  );

  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante
          rotulo="Valor aplicado"
          antes="R$"
          valor={campos.capital}
          aoMudar={mudar("capital")}
          min={0}
          max={200000}
          passo={1000}
        />
        <CampoComDeslizante
          rotulo="Taxa de juros"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          min={0}
          max={campos.unidadeDaTaxa === "ano" ? 30 : 3}
          passo={campos.unidadeDaTaxa === "ano" ? 0.5 : 0.05}
          atalhos={dados && campos.unidadeDaTaxa === "ano" ? atalhosDeJuros(dados, hoje) : []}
          depois={
            <>
              <span aria-hidden="true">%</span>
              {escolhaDaUnidade}
            </>
          }
        />
        <CampoComDeslizante
          rotulo="Prazo"
          valor={campos.prazo}
          aoMudar={mudar("prazo")}
          min={1}
          max={campos.unidadeDoPrazo === "anos" ? 50 : 360}
          passo={1}
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
        <CampoComDeslizante
          rotulo="Inflação esperada"
          valor={campos.inflacao}
          aoMudar={mudar("inflacao")}
          min={0}
          max={15}
          passo={0.25}
          atalhos={dados ? atalhosDeInflacao(dados, hoje) : []}
          depois={<span>% ao ano</span>}
          dica="Para mostrar quanto o valor final compra em dinheiro de hoje."
        />
        <label className="ferramenta-interruptor">
          <input
            type="checkbox"
            checked={comparar}
            onChange={(evento) => mudar("comparar")(evento.target.checked ? "sim" : "nao")}
          />
          Comparar com outro cenário
        </label>
        {comparar ? (
          <fieldset className="ferramenta-cenario-b">
            <legend>Cenário B (mesmo prazo e tipo de juros)</legend>
            <CampoDeNumero rotulo="Valor aplicado no cenário B" antes="R$" valor={campos.capitalB} aoMudar={mudar("capitalB")} />
            <CampoDeNumero
              rotulo="Taxa de juros do cenário B"
              valor={campos.taxaB}
              aoMudar={mudar("taxaB")}
              depois={<span>% {unidadeDaTaxa}</span>}
            />
          </fieldset>
        ) : null}
      </form>
      <Resultado rotulo="Valor no fim do prazo" principal={erro ? "" : formatarReais((conta as Conta).final)} erro={erro}>
        {erro ? null : (
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
            {inflacao !== null && inflacao > -100 ? (
              <div>
                <dt>Em reais de hoje (inflação de {formatarNumero(inflacao)}% ao ano)</dt>
                <dd>{formatarReais(emReaisDeHoje((conta as Conta).final, inflacao / 100, (conta as Conta).meses))}</dd>
              </div>
            ) : null}
            <div>
              <dt>Depois do IR, se fosse renda fixa tributada</dt>
              <dd>{formatarReais(liquidoDeIr(capital, (conta as Conta).final, (conta as Conta).meses))}</dd>
            </div>
            {contaB && typeof contaB !== "string" ? (
              <>
                <div>
                  <dt>Cenário B termina em</dt>
                  <dd>{formatarReais(contaB.final)}</dd>
                </div>
                <div>
                  <dt>Diferença (B − A)</dt>
                  <dd>{formatarReais(contaB.final - (conta as Conta).final)}</dd>
                </div>
              </>
            ) : null}
            {erroB ? <p className="ferramenta-erro">Cenário B: {erroB}</p> : null}
          </dl>
        )}
      </Resultado>
      {erro ? null : (
        <div className="ferramenta-largo">
          <GraficoDaEvolucao conta={conta as Conta} capital={capital} contaB={typeof contaB === "object" ? contaB : null} />
          <Compartilhar
            resultado={`${formatarReais(capital)} a ${formatarNumero(lerNumero(campos.taxa) ?? 0)}% ${unidadeDaTaxa} por ${prazoPorExtenso(campos)} (juros ${campos.tipo === "composto" ? "compostos" : "simples"}) dão ${formatarReais((conta as Conta).final)}`}
          />
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
        </div>
      )}
    </div>
  );
}

function GraficoDaEvolucao({ conta, capital, contaB }: { conta: Conta; capital: number; contaB: Conta | null }) {
  const pontos = pontosDoGrafico(conta.linhas);
  const meses = pontos.map((l) => l.periodo);
  if (meses.length < 2) return null;
  if (contaB) {
    const pontosB = pontosDoGrafico(contaB.linhas);
    return (
      <GraficoDoTempo
        titulo="Evolução dos dois cenários"
        meses={meses}
        series={[
          { nome: "Cenário A", cor: SERIES[0], valores: pontos.map((l) => l.montante) },
          { nome: "Cenário B", cor: SERIES[1], valores: pontosB.map((l) => l.montante) },
        ]}
        formatarValor={formatarReais}
        formatarEixo={formatarReaisCurto}
        zeroNaBase
      />
    );
  }
  return (
    <GraficoDoTempo
      titulo={`Evolução: o que foi aplicado e os juros (${formatarPorcentagem(conta.final / (capital || 1) - 1, 0)} no total)`}
      meses={meses}
      series={[
        { nome: "Valor aplicado", cor: SERIES[2], valores: pontos.map(() => capital) },
        { nome: "Juros", cor: SERIES[0], valores: pontos.map((l) => l.juros_acumulados) },
      ]}
      empilhado
      formatarValor={formatarReais}
      formatarEixo={formatarReaisCurto}
    />
  );
}
