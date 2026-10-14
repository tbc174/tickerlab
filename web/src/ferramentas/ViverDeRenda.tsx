// Viver de renda (contas/viver_de_renda.ts, a mesma conta do Python): quanto juntar e o risco de
// começar num ano ruim. Tudo em dinheiro de hoje. v2: a trajetória do patrimônio no gráfico (ano
// normal × ano ruim no começo), deslizantes e a simulação no endereço.
import { prazoPorExtenso } from "./AportesEMetas";
import { Compartilhar } from "./Compartilhar";
import { Alternativas, CampoComDeslizante, Resultado } from "./campos";
import {
  ANOS_MAXIMOS,
  duracaoEmMeses,
  patrimonioNecessario,
  rendaDaRegraDos4,
  trajetoria,
} from "./contas/viver_de_renda";
import { useCamposNoEndereco } from "./endereco";
import { formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

type Forma = "so-juros" | "gastando";
export const QUEDA_NO_PRIMEIRO_ANO = -0.3;

export const EXEMPLO_DE_RENDA = {
  renda: "5.000",
  taxa: "4",
  forma: "so-juros" as Forma,
  anos: "30",
};

const OPCOES = { forma: ["so-juros", "gastando"] } as const;
const HORIZONTE_SO_COM_OS_JUROS = 50 * 12; // o gráfico mostra 50 anos quando o dinheiro não acaba
const FOLGA_DO_GRAFICO = 5 * 12; // gastando o principal: 5 anos depois do prazo

export interface RespostaDaRenda {
  renda: number;
  taxa: number; // fração ao ano
  meses: number | null; // o prazo, gastando o principal
  patrimonio: number;
  duracaoNormal: number | null; // meses; null = mais de 100 anos
  duracaoComQueda: number | null;
  regraDos4: number;
}

/** "mais de 100 anos" ou "28 anos e 4 meses". */
export function duracaoPorExtenso(meses: number | null): string {
  return meses === null ? `mais de ${ANOS_MAXIMOS} anos` : prazoPorExtenso(meses);
}

export function calcularRenda(campos: typeof EXEMPLO_DE_RENDA): RespostaDaRenda | string {
  const renda = lerNumero(campos.renda);
  const taxa = lerNumero(campos.taxa);
  const anos = campos.forma === "gastando" ? lerNumero(campos.anos) : null;
  if (renda === null || taxa === null || (campos.forma === "gastando" && anos === null)) {
    return "Preencha os campos com números (por exemplo, 5.000).";
  }
  if (renda <= 0) return "A renda mensal precisa ser maior que zero.";
  if (anos !== null && !Number.isInteger(anos)) return "Use um prazo em anos inteiros.";
  try {
    const patrimonio = patrimonioNecessario(renda, taxa / 100, anos);
    return {
      renda,
      taxa: taxa / 100,
      meses: anos === null ? null : anos * 12,
      patrimonio,
      duracaoNormal: duracaoEmMeses(patrimonio, renda, [taxa / 100]),
      duracaoComQueda: duracaoEmMeses(patrimonio, renda, [QUEDA_NO_PRIMEIRO_ANO, taxa / 100]),
      regraDos4: rendaDaRegraDos4(patrimonio),
    };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

/** As duas trajetórias, ano a ano, no mesmo horizonte; depois que o dinheiro acaba, fica em zero. */
function trajetorias(r: RespostaDaRenda): { meses: number[]; normal: number[]; comQueda: number[] } {
  const horizonte = r.meses === null ? HORIZONTE_SO_COM_OS_JUROS : Math.min(ANOS_MAXIMOS * 12, r.meses + FOLGA_DO_GRAFICO);
  const meses: number[] = [];
  for (let mes = 0; mes <= horizonte; mes += 12) meses.push(mes);
  // a trajetória para no mês em que o dinheiro acaba; dali em diante, o saldo é zero
  const anual = (saldos: number[]) => meses.map((mes) => (mes < saldos.length ? saldos[mes] : 0));
  return {
    meses,
    normal: anual(trajetoria(r.patrimonio, r.renda, [r.taxa], horizonte)),
    comQueda: anual(trajetoria(r.patrimonio, r.renda, [QUEDA_NO_PRIMEIRO_ANO, r.taxa], horizonte)),
  };
}

export function ViverDeRenda() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DE_RENDA, OPCOES);
  const conta = calcularRenda(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante
          rotulo="Renda por mês"
          antes="R$"
          valor={campos.renda}
          aoMudar={mudar("renda")}
          min={500}
          max={50000}
          passo={500}
        />
        <CampoComDeslizante
          rotulo="Rendimento acima da inflação"
          min={0}
          max={10}
          passo={0.25}
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          depois={<span>% ao ano</span>}
          dica="O juro real: quanto o dinheiro rende além da inflação. Na dúvida, use de 3% a 5%."
        />
        <Alternativas
          rotulo="Como viver de renda"
          valor={campos.forma}
          opcoes={[
            ["so-juros", "Só com os juros (o dinheiro não acaba)"],
            ["gastando", "Gastando também o que juntei"],
          ]}
          aoMudar={mudar("forma")}
        />
        {campos.forma === "gastando" ? (
          <CampoComDeslizante
            rotulo="Por quantos anos"
            valor={campos.anos}
            aoMudar={mudar("anos")}
            min={5}
            max={60}
            passo={1}
            depois={<span>anos</span>}
          />
        ) : null}
      </form>
      <Resultado rotulo="Patrimônio necessário, em dinheiro de hoje" principal={r ? formatarReais(r.patrimonio) : ""} erro={erro}>
        {r ? (
          <dl className="ferramenta-numeros">
            <div>
              <dt>Se render isso todo ano, dura</dt>
              <dd>{duracaoPorExtenso(r.duracaoNormal)}</dd>
            </div>
            <div>
              <dt>Se o 1º ano cair 30%, dura</dt>
              <dd>{duracaoPorExtenso(r.duracaoComQueda)}</dd>
            </div>
            <div>
              <dt>Pela “regra dos 4%”, daria por mês</dt>
              <dd>{formatarReais(r.regraDos4)}</dd>
            </div>
          </dl>
        ) : null}
      </Resultado>
      {r ? <GraficoDaTrajetoria r={r} /> : null}
    </div>
  );
}

function GraficoDaTrajetoria({ r }: { r: RespostaDaRenda }) {
  const { meses, normal, comQueda } = trajetorias(r);
  return (
    <div className="ferramenta-largo">
      <GraficoDoTempo
        titulo="O patrimônio ano a ano, tirando a renda todo mês, em dinheiro de hoje"
        meses={meses}
        series={[
          { nome: "Rendendo a mesma taxa todo ano", cor: SERIES[0], valores: normal },
          { nome: "Com queda de 30% no 1º ano", cor: SERIES[1], valores: comQueda },
        ]}
        zeroNaBase
        formatarValor={formatarReais}
        formatarEixo={formatarReaisCurto}
      />
      <Compartilhar
        resultado={`Para viver com ${formatarReais(r.renda)} por mês (em dinheiro de hoje), são precisos ${formatarReais(r.patrimonio)}; com uma queda de 30% no 1º ano, dura ${duracaoPorExtenso(r.duracaoComQueda)}`}
      />
    </div>
  );
}
