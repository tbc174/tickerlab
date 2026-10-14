// Backtest simples no app novo: a estratégia escolhida, com os custos, no passado do ativo. As
// métricas saem na ordem e no formato do Streamlit (src/formatos.py) e a curva de capital em base 100.
// Monte Carlo, grade de parâmetros e proteções continuam só no app atual.
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { linkDoApp } from "../../site/textos";
import { formatar } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { BacktestDoAtivoV1 } from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

const { metricas_por_formato } = conteudoDoApp.backtest;

/** O formato de uma métrica, pelo nome (o mesmo de src/formatos.formato_da_metrica). */
function formatoDa(nome: string): string {
  const achado = Object.entries(metricas_por_formato).find(([, nomes]) => nomes.includes(nome));
  return achado ? achado[0] : "decimal";
}

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">
        <span>{rotulo}</span>
      </span>
      <span className="numero-valor">{valor}</span>
    </div>
  );
}

function Resultado({ dados }: { dados: BacktestDoAtivoV1 }) {
  const { backtest, ativo } = dados;
  return (
    <section aria-label="Resultado do backtest" className="painel-de-numeros">
      {ativo.aviso_da_origem ? (
        <p className="erro-do-app" role="note">
          {ativo.aviso_da_origem}
        </p>
      ) : null}
      <h2>{dados.estrategia}</h2>
      <div className="numeros">
        {Object.entries(backtest.metricas).map(([nome, valor]) => (
          <Numero key={nome} rotulo={nome} valor={formatar(valor, formatoDa(nome))} />
        ))}
        <Numero rotulo="Operações" valor={formatar(backtest.operacoes, "inteiro")} />
      </div>
      <h2>Curva de capital</h2>
      <GraficoDeLinha
        titulo={`Curva de capital de ${dados.estrategia} em ${ativo.ticker} (base 100)`}
        datas={backtest.curva_de_capital.datas}
        series={[{ nome: dados.estrategia, cor: "var(--serie-1)", valores: backtest.curva_de_capital.valores }]}
        referencia={100}
      />
      <p className="apagado">
        Resultado no passado, com os custos de cada operação; não é promessa de rentabilidade. Teste
        contra o acaso, Monte Carlo e grade de parâmetros estão no{" "}
        <a href={linkDoApp("backtest")}>app atual</a>.
      </p>
    </section>
  );
}

export function Backtest({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<BacktestDoAtivoV1>
      pagina={pagina}
      carregando="Rodando o backtest…"
      resultado={(dados) => <Resultado dados={dados} />}
    />
  );
}
