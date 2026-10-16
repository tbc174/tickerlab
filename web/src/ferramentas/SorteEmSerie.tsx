// Sorte em série (contas/sorte_em_serie.ts, a mesma conta do Python): estratégias de cara ou coroa,
// e a melhor parece genial. v2: as curvas com eixos e mira (em dias de pregão), o histograma do
// retorno final de todas e quantas "passariam" num teste ingênuo, com e sem a correção pelas
// tentativas. Leva à ficha "Foi sorte?", que desconta as tentativas.
import { useState } from "react";
import { Escolha, Resultado } from "./campos";
import { simular } from "./contas/sorte_em_serie";
import { formatarDecimal } from "../app/formatar";
import { formatarNumero, formatarPorcentagem, formatarReais } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDeHistograma } from "../graficos/GraficoDeHistograma";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

export const SEMENTE_INICIAL = 42;
export const EXEMPLO_DA_SORTE = { quantidade: "100" as Quantidade, anos: "1" as Anos };
const DIAS_POR_ANO_DE_PREGAO = 250; // dias de pregão num ano, para o prazo da simulação
const DIAS_POR_TRIMESTRE = 63;
const VALOR_INICIAL = 100; // as curvas em reais: "R$ 100 viraram..."

type Quantidade = "10" | "100" | "1000";
type Anos = "1" | "3" | "5";

/** As marcas do eixo em dias de pregão: trimestres no 1º ano, anos depois. */
function eixoEmDiasDePregao(dias: number) {
  const umAno = dias <= DIAS_POR_ANO_DE_PREGAO;
  const passo = umAno ? DIAS_POR_TRIMESTRE : DIAS_POR_ANO_DE_PREGAO;
  const marcas: number[] = [];
  for (let d = 0; d <= dias; d += passo) marcas.push(d);
  return {
    marcas,
    rotulo: (d: number) =>
      d === 0 ? "início" : umAno ? `${Math.round(d / DIAS_POR_TRIMESTRE) * 3} meses` : `ano ${Math.round(d / DIAS_POR_ANO_DE_PREGAO)}`,
    dica: (d: number) => (d === 0 ? "início" : `dia ${formatarNumero(d)} de pregão`),
  };
}

const sinal = (fracao: number) => `${fracao > 0 ? "+" : ""}${formatarPorcentagem(fracao, 0)}`;

export function SorteEmSerie() {
  const [quantidade, setQuantidade] = useState<Quantidade>(EXEMPLO_DA_SORTE.quantidade);
  const [anos, setAnos] = useState<Anos>(EXEMPLO_DA_SORTE.anos);
  const [semente, setSemente] = useState(SEMENTE_INICIAL);
  const r = simular(Number(quantidade), Number(anos) * DIAS_POR_ANO_DE_PREGAO, semente);
  const total = formatarNumero(r.estrategias);
  const dias = Array.from({ length: r.dias + 1 }, (_, d) => d);
  const emReais = (curva: number[]) => curva.map((v) => v * VALOR_INICIAL);
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <p>
          Cada estratégia ganha ou perde 1% por dia no cara ou coroa. Nenhuma tem vantagem: todas
          são moeda.
        </p>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Quantas estratégias</span>
          <Escolha
            rotulo="Quantas estratégias"
            valor={quantidade}
            opcoes={[
              ["10", "10"],
              ["100", "100"],
              ["1000", "1.000"],
            ]}
            aoMudar={setQuantidade}
          />
        </div>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Por quanto tempo</span>
          <Escolha
            rotulo="Por quanto tempo"
            valor={anos}
            opcoes={[
              ["1", "1 ano"],
              ["3", "3 anos"],
              ["5", "5 anos"],
            ]}
            aoMudar={setAnos}
          />
        </div>
        <button className="botao secundario" type="button" onClick={() => setSemente((s) => s + 1)}>
          Sortear de novo
        </button>
      </form>
      <Resultado rotulo={`A melhor de ${total}`} principal={formatarPorcentagem(r.retorno_da_melhor)} erro={null}>
        <dl className="ferramenta-numeros">
          <div>
            <dt>Sharpe da melhor</dt>
            <dd>{formatarDecimal(r.sharpe_da_melhor)}</dd>
          </div>
          <div>
            <dt>Com Sharpe acima de 1</dt>
            <dd>
              {formatarNumero(r.com_sharpe_acima_de_1)} de {total}
            </dd>
          </div>
          <div>
            <dt>Terminaram no lucro</dt>
            <dd>
              {formatarNumero(r.lucraram)} de {total}
            </dd>
          </div>
          <div>
            <dt>A do meio terminou em</dt>
            <dd>{formatarPorcentagem(r.retorno_da_mediana)}</dd>
          </div>
        </dl>
        <p className="ferramenta-destaque">
          Num teste ingênuo (a média é maior que zero, com 5% de chance de erro), {formatarNumero(r.passam_sem_correcao)} de{" "}
          {total} passariam como "estratégias que funcionam". Mas, corrigindo pelas {total} tentativas,{" "}
          {formatarNumero(r.passam_com_correcao)}. Todas são moeda.
        </p>
      </Resultado>
      <div className="ferramenta-largo">
        <GraficoDoTempo
          titulo="R$ 100 na melhor, na do meio e na pior estratégia, dia a dia"
          meses={dias}
          series={[
            { nome: "A melhor", cor: SERIES[0], valores: emReais(r.curva_da_melhor) },
            { nome: "A do meio", cor: SERIES[2], valores: emReais(r.curva_da_mediana) },
            { nome: "A pior", cor: SERIES[1], valores: emReais(r.curva_da_pior) },
          ]}
          referencia={{ valor: VALOR_INICIAL, rotulo: "Começo" }}
          eixoX={eixoEmDiasDePregao(r.dias)}
          formatarValor={formatarReais}
          formatarEixo={(v) => `R$ ${formatarNumero(v)}`}
        />
        <GraficoDeHistograma
          titulo={`Onde as ${total} estratégias terminaram`}
          valores={r.retornos_finais}
          formatarFaixa={sinal}
          nomeDaContagem="estratégias"
        />
        <p className="apagado">
          Cada barra conta quantas estratégias terminaram naquela faixa de retorno. A maioria fica perto de zero; a
          "genial" é só a ponta da direita.
        </p>
      </div>
    </div>
  );
}
