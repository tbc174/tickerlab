// O cartão "Estratégias acompanhadas" do Workspace (ADR 0062; Workspace, PR 2): os backtests salvos com a
// ficha "Foi sorte?", que o Pulse refaz com os preços de hoje. A API já manda na ordem do cartão (o que
// mudou, as iguais, as não conferidas); aqui só se mostra. O pedido ao Pulse é do Início (usarPulse).
import { Link } from "react-router";
import { conteudoDoApp } from "../../../conteudo";
import { linkDoApp } from "../../../site/textos";
import type { EstrategiaAcompanhadaV1, PulseV1 } from "../../tipos";
import { Vazio } from "../../Vazio";

const TERMO_DA_FICHA = conteudoDoApp.backtest.ficha.termo;
const SIMBOLO_DO_VEREDITO: Record<string, string> = { passou: "✓", "não passou": "✕", inconclusivo: "?" };

/** "2026-10-09T23:00:00Z" → "09/10" (no horário de Brasília, como as datas do Pulse no app atual). */
function diaEMes(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "America/Sao_Paulo" });
}

function Situacao({ e }: { e: EstrategiaAcompanhadaV1 }) {
  if (e.agora === null) {
    return <p className="apagado">Não deu para conferir agora{e.antes ? ` (da última vez: ${e.antes})` : ""}.</p>;
  }
  if (e.mudou) {
    return (
      <p className="selo-da-mudanca">
        <span aria-hidden="true">{SIMBOLO_DO_VEREDITO[e.agora] ?? "?"} </span>
        {TERMO_DA_FICHA} <span>{`${e.antes} → ${e.agora}${e.conferido_em ? ` · ${diaEMes(e.conferido_em)}` : ""}`}</span>
      </p>
    );
  }
  return (
    <p className="apagado">
      {TERMO_DA_FICHA} {e.agora} · sem mudança
    </p>
  );
}

function Estrategia({ e }: { e: EstrategiaAcompanhadaV1 }) {
  return (
    <li className={e.mudou ? "mudou" : undefined}>
      <div>
        <strong>{e.nome}</strong>
        {e.ticker ? <span className="apagado"> · {e.ticker.replace(/\.SA$/, "")}</span> : null}
        <Situacao e={e} />
        {/* a tese é texto da pessoa (o React escapa); como no app atual, só junto do que mudou */}
        {e.mudou && e.tese_ligada ? <p className="tese-ligada">{e.tese_ligada}</p> : null}
      </div>
      <div className="acoes-da-simulacao">
        {e.endereco ? (
          <Link className="botao pequeno" to={e.endereco}>
            Abrir o backtest
          </Link>
        ) : (
          <a className="botao pequeno" href={linkDoApp("simulacoes")}>
            Abrir no app atual
          </a>
        )}
      </div>
    </li>
  );
}

export function EstrategiasAcompanhadas({ dados }: { dados: PulseV1 }) {
  return (
    <section className="cartao-do-workspace" aria-labelledby="titulo-das-estrategias">
      <h2 id="titulo-das-estrategias">Estratégias acompanhadas</h2>
      {dados.estrategias.length === 0 ? (
        <Vazio frase={dados.sem_estrategias} acao={{ texto: "Rodar um backtest", para: "/backtest" }} />
      ) : (
        <ul className="links-da-conta lista-de-simulacoes" aria-label="Estratégias">
          {dados.estrategias.map((e) => (
            <Estrategia key={e.id} e={e} />
          ))}
        </ul>
      )}
      {dados.avisos.map((aviso) => (
        <p key={aviso} className="legenda-do-numero">
          {aviso}
        </p>
      ))}
      {dados.notas.map((nota) => (
        <p key={nota} className="legenda-do-numero">
          {nota}
        </p>
      ))}
    </section>
  );
}
