// Conversor de moedas pela PTAX do Banco Central (contas/moedas.ts, a mesma conta do Python), v2:
// inverter de/para, a variação em 30 dias e em 12 meses, o gráfico de 12 meses da PTAX de venda e a
// simulação no endereço.
import { Compartilhar } from "./Compartilhar";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { ComDadosDoBc, DataDoDado } from "./Carregando";
import { REAL, converter } from "./contas/moedas";
import { type DadosDoBc, type Moeda, dataBrasileira, useDadosDoBc } from "./dados";
import { useCamposNoEndereco } from "./endereco";
import { formatarPorcentagem, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

export const EXEMPLO_DO_CONVERSOR = { valor: "100", de: "USD", para: REAL };
// as moedas da PTAX (o endereço só aceita estas; uma nova do BC aparece na lista, sem o endereço)
const CODIGOS = [REAL, "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "DKK", "SEK", "NOK"];
const OPCOES = { de: CODIGOS, para: CODIGOS } as const;
const MS_POR_DIA = 24 * 3600 * 1000;
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** A variação da cotação mais nova contra a do último dia até `dias` antes dela; null sem dado. */
export function variacao(historico: [string, number][], dias: number): number | null {
  if (historico.length < 2) return null;
  const [ultimoDia, ultima] = historico[historico.length - 1];
  const limite = new Date(new Date(`${ultimoDia}T12:00:00`).getTime() - dias * MS_POR_DIA).toISOString().slice(0, 10);
  const antes = [...historico].reverse().find(([dia]) => dia <= limite);
  return antes ? ultima / antes[1] - 1 : null;
}

/** "out/25": o rótulo de um mês no eixo do gráfico. */
const mesCurto = (iso: string) => `${MESES[Number(iso.slice(5, 7)) - 1]}/${iso.slice(2, 4)}`;

function GraficoDaMoeda({ moeda }: { moeda: Moeda }) {
  const historico = moeda.historico ?? [];
  if (historico.length < 2) return null;
  // eixo x: o índice do dia de pregão; marcas no 1º pregão de cada trimestre
  const marcas = historico.flatMap(([dia], i) => {
    const mes = Number(dia.slice(5, 7));
    const comecaOMes = i > 0 && dia.slice(5, 7) !== historico[i - 1][0].slice(5, 7);
    return i === 0 || (comecaOMes && mes % 3 === 1) ? [i] : [];
  });
  const formatar = (v: number) => formatarNaMoeda(v, REAL);
  return (
    <GraficoDoTempo
      titulo={`${moeda.nome}: a PTAX de venda nos últimos 12 meses, em reais`}
      meses={historico.map((_, i) => i)}
      series={[{ nome: moeda.codigo, cor: SERIES[0], valores: historico.map(([, v]) => v) }]}
      eixoX={{
        marcas,
        rotulo: (i) => mesCurto(historico[i][0]),
        dica: (i) => dataBrasileira(historico[i][0]),
      }}
      formatarValor={formatar}
      formatarEixo={formatar}
    />
  );
}

/** "US$ 100,00", "€ 89,30", "R$ 500,00": o valor com o símbolo da moeda. Código que o navegador
 * não conhece (o BC pode acrescentar uma moeda) sai como "1.234,56 XYZ", sem quebrar a página. */
export function formatarNaMoeda(valor: number, codigo: string): string {
  const casas = codigo === "JPY" ? 0 : 2;
  try {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: codigo,
      minimumFractionDigits: casas,
      maximumFractionDigits: casas,
    }).format(valor);
  } catch (erro) {
    if (!(erro instanceof RangeError)) throw erro;
    const numero = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
    return `${numero.format(valor)} ${codigo}`;
  }
}

export function cotacoesDeVenda(moedas: Moeda[]): Record<string, number> {
  return Object.fromEntries(moedas.map((m) => [m.codigo, m.venda]));
}

function Conversor({ moedas }: { moedas: Moeda[] }) {
  const [campos, mudar, definir] = useCamposNoEndereco(EXEMPLO_DO_CONVERSOR, OPCOES);
  const opcoes: [string, string][] = [[REAL, "Real (BRL)"], ...moedas.map((m): [string, string] => [m.codigo, `${m.nome} (${m.codigo})`])];
  const valor = lerNumero(campos.valor);
  const cotacoes = cotacoesDeVenda(moedas);
  const estrangeira = moedas.find((m) => m.codigo === (campos.de === REAL ? campos.para : campos.de));
  const resultado = valor === null ? null : converter(valor, campos.de, campos.para, cotacoes);
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor" valor={campos.valor} aoMudar={mudar("valor")} />
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">De</span>
          <Escolha rotulo="De" valor={campos.de} opcoes={opcoes} aoMudar={mudar("de")} />
        </div>
        <button
          type="button"
          className="botao secundario pequeno ferramenta-inverter"
          aria-label="Inverter de e para"
          onClick={() => definir((antes) => ({ ...antes, de: antes.para, para: antes.de }))}
        >
          ⇅ Inverter
        </button>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Para</span>
          <Escolha rotulo="Para" valor={campos.para} opcoes={opcoes} aoMudar={mudar("para")} />
        </div>
      </form>
      <Resultado
        rotulo={valor === null ? "" : `${formatarNaMoeda(valor, campos.de)} são`}
        principal={resultado === null ? "" : formatarNaMoeda(resultado, campos.para)}
        erro={valor === null ? "Digite o valor em números (por exemplo, 1.000,50)." : null}
      >
        {estrangeira ? (
          <>
            <p>
              1 {estrangeira.codigo} = {formatarNaMoeda(estrangeira.venda, REAL)} pela PTAX de venda.
            </p>
            <DataDoDado data={estrangeira.data} rotulo="PTAX de fechamento de" />
            <dl className="ferramenta-numeros">
              {([
                [30, "Em 30 dias"],
                [365, "Em 12 meses"],
              ] as const).map(([dias, rotulo]) => {
                const v = variacao(estrangeira.historico ?? [], dias);
                return v === null ? null : (
                  <div key={dias}>
                    <dt>
                      {rotulo}: {formatarPorcentagem(v)}
                    </dt>
                    <dd>{v > 0 ? "o real perdeu valor" : "o real ganhou valor"}</dd>
                  </div>
                );
              })}
            </dl>
          </>
        ) : null}
      </Resultado>
      {estrangeira?.historico && estrangeira.historico.length > 1 ? (
        <div className="ferramenta-largo">
          <GraficoDaMoeda moeda={estrangeira} />
          {valor !== null && resultado !== null ? (
            <Compartilhar
              resultado={`${formatarNaMoeda(valor, campos.de)} = ${formatarNaMoeda(resultado, campos.para)} pela PTAX de ${dataBrasileira(estrangeira.data)} (Banco Central)`}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ConversorDeMoedas() {
  const carga = useDadosDoBc();
  return (
    <ComDadosDoBc carga={carga}>
      {(dados: DadosDoBc) =>
        dados.moedas?.length ? <Conversor moedas={dados.moedas} /> : <p className="ferramenta-erro">Sem a PTAX agora.</p>
      }
    </ComDadosDoBc>
  );
}
