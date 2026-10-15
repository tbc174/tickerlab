// Fundo × CDB (contas/fundos.ts e contas/renda_fixa.ts, as mesmas contas do Python): um fundo de
// renda fixa pelo CDI, com taxa de administração, de performance e come-cotas, contra um CDB do mesmo
// prazo e do mesmo CDI (o de hoje, parado). O fundo vira "um CDB de X% do CDI"; o gráfico mostra o
// que cada um daria, já sem IR, se resgatasse no fim de cada mês.
import { Compartilhar } from "./Compartilhar";
import { Alternativas, CampoComDeslizante, Resultado } from "./campos";
import { ComDadosDoBc, DataDoDado } from "./Carregando";
import { DIAS_POR_MES, PRAZO_MAXIMO, type Resultado as Fundo, simular } from "./contas/fundos";
import { type Opcao, cdbQueRende, comparar } from "./contas/renda_fixa";
import { type DadosDoBc, useDadosDoBc } from "./dados";
import { useCamposNoEndereco } from "./endereco";
import { formatarPorcentagem, formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

type Prazo = "longo" | "curto";

export const EXEMPLO_DO_FUNDO = {
  valor: "10.000",
  anos: "3",
  fundo: "100",
  administracao: "1",
  performance: "0",
  prazo: "longo" as Prazo,
  cdb: "100",
};
const OPCOES = { prazo: ["longo", "curto"] } as const;
type Campos = typeof EXEMPLO_DO_FUNDO;

export interface ComparacaoDoFundo {
  valor: number;
  fundo: Fundo;
  cdb: Opcao;
  equivalente: number | null; // o % do CDI de um CDB que rende o mesmo que o fundo
  meses: number;
}

const SEM_POUPANCA = 0; // comparar() também devolve a poupança, que esta página não usa

const diasDe = (meses: number) => Math.round(meses * DIAS_POR_MES);

interface Numeros {
  valor: number;
  meses: number;
  fundo: number; // frações: 1 = 100% do CDI
  administracao: number;
  performance: number;
  longoPrazo: boolean;
  cdb: number;
}

function lerCampos(campos: Campos): Numeros | string {
  const lidos = [campos.valor, campos.anos, campos.fundo, campos.administracao, campos.performance, campos.cdb].map((t) =>
    t.trim() === "" ? 0 : lerNumero(t),
  );
  if (lidos.some((n) => n === null)) return "Preencha os campos com números (por exemplo, 10.000).";
  const [valor, anos, fundo, administracao, performance, cdb] = lidos as number[];
  const meses = Math.round(anos * 12);
  if (meses > PRAZO_MAXIMO) return `O prazo vai até ${PRAZO_MAXIMO / 12} anos.`;
  const fracao = (n: number) => n / 100;
  return {
    valor,
    meses,
    fundo: fracao(fundo),
    administracao: fracao(administracao),
    performance: fracao(performance),
    longoPrazo: campos.prazo === "longo",
    cdb: fracao(cdb),
  };
}

/** O fundo e o CDB resgatados depois de `meses` meses. */
function resgatar(n: Numeros, meses: number, cdiAoAno: number, mesInicial: number): { fundo: Fundo; cdb: Opcao } {
  return {
    fundo: simular(n.valor, meses, cdiAoAno, n.fundo, n.administracao, n.performance, n.longoPrazo, mesInicial),
    cdb: comparar(n.valor, diasDe(meses), [cdiAoAno], n.cdb, 0, SEM_POUPANCA)[0],
  };
}

/** O fundo e o CDB pelos campos, com o CDI ao ano e o mês de hoje, ou a mensagem quando algo não fecha. */
export function calcularFundo(campos: Campos, cdiAoAno: number, mesInicial: number): ComparacaoDoFundo | string {
  const n = lerCampos(campos);
  if (typeof n === "string") return n;
  try {
    const { fundo, cdb } = resgatar(n, n.meses, cdiAoAno, mesInicial);
    const equivalente = cdbQueRende(n.valor, diasDe(n.meses), [cdiAoAno], fundo.liquido);
    return { valor: n.valor, fundo, cdb, equivalente, meses: n.meses };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

/** O líquido de cada um se resgatasse no fim de cada mês (o mês 0 é o valor aplicado); a conta
 * do prazo inteiro já passou, então nenhum mês antes dele recusa. */
export function curvas(campos: Campos, cdiAoAno: number, mesInicial: number) {
  const n = lerCampos(campos) as Numeros;
  const fundo = [n.valor];
  const cdb = [n.valor];
  for (let m = 1; m <= n.meses; m++) {
    const r = resgatar(n, m, cdiAoAno, mesInicial);
    fundo.push(r.fundo.liquido);
    cdb.push(r.cdb.liquido);
  }
  return { fundo, cdb };
}

function Comparacao({ dados }: { dados: DadosDoBc }) {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DO_FUNDO, OPCOES);
  const cdi = dados.cdi!;
  const mesInicial = new Date().getMonth() + 1;
  const conta = calcularFundo(campos, cdi.ao_ano, mesInicial);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  const linhas = r ? curvas(campos, cdi.ao_ano, mesInicial) : null;
  const diferenca = r ? r.fundo.liquido - r.cdb.liquido : 0;
  const equivalente =
    r && r.equivalente !== null ? `um CDB de ${formatarPorcentagem(r.equivalente, 1)} do CDI` : "mais de 1.000% do CDI";
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante rotulo="Valor aplicado" antes="R$" valor={campos.valor} aoMudar={mudar("valor")} min={1000} max={1000000} passo={1000} />
        <CampoComDeslizante rotulo="Prazo" valor={campos.anos} aoMudar={mudar("anos")} min={1} max={30} passo={1} depois={<span>anos</span>} />
        <fieldset className="ferramenta-cenario-b">
          <legend>O fundo</legend>
          <CampoComDeslizante rotulo="Rende" valor={campos.fundo} aoMudar={mudar("fundo")} min={50} max={150} passo={1} depois={<span>% do CDI, antes das taxas</span>} />
          <CampoComDeslizante
            rotulo="Taxa de administração"
            valor={campos.administracao}
            aoMudar={mudar("administracao")}
            min={0}
            max={3}
            passo={0.05}
            depois={<span>% ao ano</span>}
          />
          <CampoComDeslizante
            rotulo="Taxa de performance"
            valor={campos.performance}
            aoMudar={mudar("performance")}
            min={0}
            max={30}
            passo={1}
            depois={<span>% do que passar do CDI</span>}
          />
          <Alternativas
            rotulo="Tipo"
            valor={campos.prazo}
            opcoes={[
              ["longo", "Longo prazo (15%)"],
              ["curto", "Curto prazo (20%)"],
            ]}
            aoMudar={mudar("prazo")}
          />
        </fieldset>
        <CampoComDeslizante rotulo="CDB que paga" valor={campos.cdb} aoMudar={mudar("cdb")} min={80} max={150} passo={1} depois={<span>% do CDI</span>} />
      </form>
      <Resultado rotulo="Depois das taxas e do IR, este fundo rende como" principal={r ? equivalente : ""} erro={erro}>
        {r ? (
          <>
            <p className="ferramenta-destaque">
              {diferenca < 0
                ? `O CDB de ${campos.cdb}% do CDI deixa ${formatarReais(-diferenca)} a mais no bolso.`
                : `O fundo deixa ${formatarReais(diferenca)} a mais no bolso que o CDB de ${campos.cdb}% do CDI.`}
            </p>
            <table className="ferramenta-comparacao">
              <thead>
                <tr>
                  <th scope="col" />
                  <th scope="col">Fundo</th>
                  <th scope="col">CDB</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Taxa de administração</th>
                  <td>{formatarReais(r.fundo.taxa_de_administracao)}</td>
                  <td>—</td>
                </tr>
                <tr>
                  <th scope="row">Taxa de performance</th>
                  <td>{formatarReais(r.fundo.taxa_de_performance)}</td>
                  <td>—</td>
                </tr>
                <tr>
                  <th scope="row">Come-cotas ({r.fundo.vezes_do_come_cotas}×)</th>
                  <td>{formatarReais(r.fundo.come_cotas)}</td>
                  <td>—</td>
                </tr>
                <tr>
                  <th scope="row">IR no resgate</th>
                  <td>{formatarReais(r.fundo.ir_no_resgate)}</td>
                  <td>{formatarReais(r.cdb.imposto + r.cdb.iof)}</td>
                </tr>
                <tr>
                  <th scope="row">Líquido no resgate</th>
                  <td>{formatarReais(r.fundo.liquido)}</td>
                  <td>{formatarReais(r.cdb.liquido)}</td>
                </tr>
              </tbody>
            </table>
          </>
        ) : null}
        <DataDoDado data={cdi.data} rotulo={`CDI de ${formatarPorcentagem(cdi.ao_ano)} ao ano, de`} />
      </Resultado>
      {r && linhas ? (
        <div className="ferramenta-largo">
          <GraficoDoTempo
            titulo="Quanto cada um daria, já sem IR, se resgatasse no fim de cada mês"
            meses={linhas.fundo.map((_, m) => m)}
            series={[
              { nome: "Fundo", cor: SERIES[0], valores: linhas.fundo },
              { nome: "CDB", cor: SERIES[1], valores: linhas.cdb },
            ]}
            formatarValor={formatarReais}
            formatarEixo={formatarReaisCurto}
          />
          <Compartilhar
            resultado={`Um fundo de ${campos.fundo}% do CDI com ${campos.administracao}% de administração, em ${campos.anos} anos, rende como ${equivalente}`}
          />
        </div>
      ) : null}
    </div>
  );
}

export function FundosERendaFixa() {
  const carga = useDadosDoBc();
  return (
    <ComDadosDoBc carga={carga}>
      {(dados) => (dados.cdi ? <Comparacao dados={dados} /> : <p className="ferramenta-erro">Sem o CDI agora.</p>)}
    </ComDadosDoBc>
  );
}
