// Retorno por mês e ano no app novo: o melhor e o pior mês, os meses de alta (os mesmos cartões do
// Streamlit) e o mapa com um ano por linha, a média de cada mês e o ano inteiro.
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { Ajuda } from "../Ajuda";
import { formatarPct } from "../formatar";
import type { MesV1, RetornoMensalDoAtivoV1 } from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

const { meses: NOMES_DOS_MESES, legenda } = conteudoDoApp.retorno_mensal;
const INTENSIDADE_MAXIMA = 0.1; // 10% num mês já pinta a célula com a cor cheia

/** "2026-03" → "Mar/2026", como os cartões do Streamlit. */
function nomeDoMes(mes: MesV1): string {
  const [ano, numero] = mes.mes.split("-");
  return `${NOMES_DOS_MESES[Number(numero) - 1]}/${ano}`;
}

/** A cor da célula: verde (alta) ou vermelho (queda), mais forte quanto maior o retorno. */
function corDaCelula(valor: number | null): React.CSSProperties | undefined {
  if (valor === null || valor === 0) return undefined;
  const forca = Math.round(Math.min(1, Math.abs(valor) / INTENSIDADE_MAXIMA) * 45);
  return { background: `color-mix(in srgb, var(${valor > 0 ? "--alta" : "--queda"}) ${forca}%, transparent)` };
}

function Cartao({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">
        <span>{rotulo}</span>
        <Ajuda termo="Retorno mensal" rotulo={rotulo} />
      </span>
      <span className="numero-valor">{valor}</span>
    </div>
  );
}

function Celula({ valor }: { valor: number | null }) {
  return (
    <td className="numero" style={corDaCelula(valor)}>
      {formatarPct(valor, true)}
    </td>
  );
}

function Resultado({ dados }: { dados: RetornoMensalDoAtivoV1 }) {
  const mensal = dados.retorno_mensal;
  return (
    <section aria-label="Retorno por mês e ano">
      {dados.ativo.aviso_da_origem ? (
        <p className="erro-do-app" role="note">
          {dados.ativo.aviso_da_origem}
        </p>
      ) : null}
      <h2>
        Retorno por mês e ano <Ajuda termo="Sazonalidade" rotulo="retorno por mês e ano" />
      </h2>
      <div className="numeros">
        <Cartao rotulo={`Melhor mês (${nomeDoMes(mensal.melhor)})`} valor={formatarPct(mensal.melhor.retorno, true)} />
        <Cartao rotulo={`Pior mês (${nomeDoMes(mensal.pior)})`} valor={formatarPct(mensal.pior.retorno, true)} />
        <Cartao rotulo="Meses de alta" valor={formatarPct(mensal.meses_de_alta)} />
      </div>
      <div className="tabela-rolavel">
        <table className="tabela-do-app mapa-mensal">
          <caption>Retorno de cada mês, com o ano inteiro na última coluna</caption>
          <thead>
            <tr>
              <th scope="col">Ano</th>
              {NOMES_DOS_MESES.map((m) => (
                <th key={m} scope="col">
                  {m}
                </th>
              ))}
              <th scope="col">No ano</th>
            </tr>
          </thead>
          <tbody>
            {mensal.tabela.map((linha) => (
              <tr key={linha.ano}>
                <th scope="row">{linha.ano}</th>
                {linha.meses.map((valor, i) => (
                  <Celula key={NOMES_DOS_MESES[i]} valor={valor} />
                ))}
                <Celula valor={linha.total} />
              </tr>
            ))}
            <tr>
              <th scope="row">Média do mês</th>
              {mensal.media_por_mes.map((valor, i) => (
                <Celula key={NOMES_DOS_MESES[i]} valor={valor} />
              ))}
              <td />
            </tr>
          </tbody>
        </table>
      </div>
      <p className="apagado">{legenda}</p>
    </section>
  );
}

export function RetornoMensal({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<RetornoMensalDoAtivoV1>
      pagina={pagina}
      carregando="Calculando os meses…"
      esqueleto="lista"
      resultado={(dados) => <Resultado dados={dados} />}
    />
  );
}
