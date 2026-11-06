// Comparar ativos no app novo: o ativo do topo contra os atalhos (Ibovespa, S&P 500...) e outros
// tickers, em base 100 nos dias em comum, com a tabela formatada como no Streamlit.
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { Ajuda } from "../Ajuda";
import { itensDaLista } from "../Formulario";
import { formatar } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { ComparacaoDoAtivoV1, LinhaDaComparacaoV1 } from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

const { atalhos, max_ativos, colunas, aviso_do_limite, aviso_sem_dados } = conteudoDoApp.comparacao;
const NOMES: Record<string, string> = Object.fromEntries(atalhos.map((a) => [a.ticker, a.nome]));
/** O nome do atalho (Ibovespa) ou o código da tela (PETR4), nunca o símbolo do Yahoo. */
const nomeDo = (ticker: string, codigos: Record<string, string>) =>
  NOMES[ticker] ?? codigos[ticker] ?? ticker;
// o rótulo de cada coluna (src/comparacao.FORMATO_DAS_COLUNAS) → o campo da resposta da API
const CAMPOS: Record<string, keyof LinhaDaComparacaoV1> = {
  "Retorno total": "retorno_total",
  "Retorno anualizado": "retorno_anualizado",
  "Volatilidade anual": "volatilidade_anual",
  "Maior queda": "maior_queda",
  "Índice de Sharpe": "sharpe",
};

/** O ativo do topo conta no limite: passam só os primeiros `max_ativos - 1` da lista. */
function limitar(valores: Record<string, string>) {
  const itens = itensDaLista(valores.com ?? "").filter((t) => t !== (valores.ticker ?? "").toUpperCase());
  const dentro = itens.slice(0, max_ativos - 1);
  const fora = itens.slice(max_ativos - 1);
  const aviso = fora.length
    ? aviso_do_limite.replace("{maximo}", String(max_ativos)).replace("{fora}", fora.join(", "))
    : null;
  return { valores: { ...valores, com: dentro.join(",") }, aviso };
}

function codigosDa(linhas: LinhaDaComparacaoV1[] | null): Record<string, string> {
  return Object.fromEntries((linhas ?? []).map((l) => [l.ticker, l.codigo]));
}

function Tabela({ linhas }: { linhas: LinhaDaComparacaoV1[] }) {
  const codigos = codigosDa(linhas);
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <caption>Números no mesmo período</caption>
        <thead>
          <tr>
            <th scope="col">Ativo</th>
            {colunas.map((c) => (
              <th key={c.rotulo} scope="col">
                {c.rotulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha) => (
            <tr key={linha.ticker}>
              <th scope="row">{nomeDo(linha.ticker, codigos)}</th>
              {colunas.map((c) => (
                <td key={c.rotulo} className="numero">
                  {formatar(linha[CAMPOS[c.rotulo]] as number | null, c.formato)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Resultado({ dados }: { dados: ComparacaoDoAtivoV1 }) {
  const { comparacao } = dados;
  const curvas = comparacao.curvas ? Object.entries(comparacao.curvas) : [];
  const codigos = codigosDa(comparacao.tabela);
  return (
    <>
      {dados.sem_dados.length ? (
        <p className="erro-do-app" role="note">
          {aviso_sem_dados.replace("{sem_dados}", dados.sem_dados.join(", "))}
        </p>
      ) : null}
      {comparacao.aviso ? <p className="erro-do-app">{comparacao.aviso}</p> : null}
      {curvas.length > 0 ? (
        <>
          <h2>
            Em base 100 <Ajuda termo="Base 100" rotulo="base 100" />
          </h2>
          <GraficoDeLinha
            titulo={`${curvas.map(([t]) => nomeDo(t, codigos)).join(", ")} em base 100`}
            datas={curvas[0][1].datas}
            series={curvas.map(([ticker, curva], i) => ({
              nome: nomeDo(ticker, codigos),
              cor: `var(--serie-${i + 1})`,
              valores: curva.valores,
            }))}
            referencia={100}
          />
        </>
      ) : null}
      {comparacao.tabela ? <Tabela linhas={comparacao.tabela} /> : null}
      {comparacao.nota ? <p className="apagado">{comparacao.nota}</p> : null}
    </>
  );
}

export function Comparar({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<ComparacaoDoAtivoV1>
      pagina={pagina}
      carregando="Comparando…"
      esqueleto="grafico"
      resultado={(dados) => <Resultado dados={dados} />}
      ajustar={limitar}
    />
  );
}
