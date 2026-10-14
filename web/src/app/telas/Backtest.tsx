// Backtest simples no app novo: a estratégia escolhida, com os custos, no passado do ativo. As
// métricas saem na ordem e no formato do Streamlit (src/formatos.py) e a curva de capital em base 100.
// Embaixo, a ficha "Foi sorte?" (src/ficha.py, pela API). Proteções, Monte Carlo e o detalhe técnico
// da validação continuam só no app atual.
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { linkDoApp } from "../../site/textos";
import { Ajuda } from "../Ajuda";
import { VereditoDaFicha } from "../VereditoDaFicha";
import { formatar } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { BacktestDoAtivoV1, FichaV1 } from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

const { metricas_por_formato, ficha: textosDaFicha } = conteudoDoApp.backtest;

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

function Ficha({ ficha }: { ficha: FichaV1 }) {
  const { veredito } = ficha;
  return (
    <>
      <VereditoDaFicha
        resultado={veredito.resultado}
        titulo={veredito.titulo}
        texto={veredito.texto}
        checagens={ficha.checagens}
        nivel={3}
      />
      <p>{ficha.texto_das_tentativas}</p>
      <p className="apagado">{ficha.nota}</p>
    </>
  );
}

/** A seção "Foi sorte?": a ficha ou, sem ela, o motivo (o backtest em cima continua valendo). */
function FoiSorte({ dados }: { dados: BacktestDoAtivoV1 }) {
  return (
    <section aria-label={textosDaFicha.termo} className="ficha-foi-sorte">
      <h2>
        {textosDaFicha.termo}
        <Ajuda termo={textosDaFicha.termo} rotulo={textosDaFicha.termo} />
      </h2>
      <p className="apagado">{textosDaFicha.explicacao}</p>
      {dados.ficha ? (
        <Ficha ficha={dados.ficha} />
      ) : (
        <p className="erro-do-app" role="note">
          {dados.motivo_sem_ficha}
        </p>
      )}
    </section>
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
        Resultado no passado, com os custos de cada operação; não é promessa de rentabilidade. Proteções
        (stop, alvo), Monte Carlo e o detalhe técnico da validação estão no{" "}
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
      resultado={(dados) => (
        <>
          <Resultado dados={dados} />
          <FoiSorte dados={dados} />
        </>
      )}
    />
  );
}
