// O cartão "Estratégias acompanhadas" do Workspace (ADR 0062; Workspace, PR 2): os backtests salvos com a
// ficha "Foi sorte?", que o Pulse refaz com os preços de hoje. A API já manda na ordem do cartão (o que
// mudou, as iguais, as não conferidas); aqui só se mostra.
//
// Abrir o Pulse marca a visita. Sem sessão no servidor, a aba guarda o início da janela que mostrou e o
// reenvia em `desde` no F5: senão a janela encolheria para os segundos desde a visita que ela mesma marcou.
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { conteudoDoApp } from "../../../conteudo";
import { linkDoApp } from "../../../site/textos";
import type { EstrategiaAcompanhadaV1, PulseV1 } from "../../tipos";
import { usarPedido } from "../../usarPedido";
import { ErroDaTela } from "../ErroDaTela";

const ROTA_DO_PULSE = "/v1/pulse";
const CHAVE_DA_JANELA = "tickerlab.workspace.inicio-da-janela";
const TERMO_DA_FICHA = conteudoDoApp.backtest.ficha.termo;
const SIMBOLO_DO_VEREDITO: Record<string, string> = { passou: "✓", "não passou": "✕", inconclusivo: "?" };

/** O início da janela que esta aba já mostrou (o sessionStorage pode faltar: aba anônima, bloqueio). */
function inicioGuardado(): string | undefined {
  try {
    const guardado = sessionStorage.getItem(CHAVE_DA_JANELA);
    return guardado && !Number.isNaN(Date.parse(guardado)) ? guardado : undefined;
  } catch {
    return undefined;
  }
}

function guardarInicio(inicio: string) {
  try {
    sessionStorage.setItem(CHAVE_DA_JANELA, inicio);
  } catch {
    // sem sessionStorage, o F5 volta à janela desde a última visita: nada quebra
  }
}

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

function Conteudo({ dados }: { dados: PulseV1 }) {
  return (
    <>
      <p className="apagado">{dados.janela.texto}</p>
      {dados.estrategias.length === 0 ? (
        <p>
          {dados.sem_estrategias}{" "}
          <Link className="botao pequeno" to="/backtest">
            Rodar um backtest
          </Link>
        </p>
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
    </>
  );
}

export function EstrategiasAcompanhadas() {
  // lido uma vez só: os parâmetros não mudam depois, e a página pede o Pulse uma vez
  const [parametros] = useState(() => ({ desde: inicioGuardado() }));
  const pedido = usarPedido<PulseV1>(ROTA_DO_PULSE, parametros);
  const inicio = pedido.estado === "pronto" ? pedido.dados.janela.inicio : null;
  useEffect(() => {
    if (inicio !== null) guardarInicio(inicio);
  }, [inicio]);
  return (
    <section className="cartao-do-workspace" aria-labelledby="titulo-das-estrategias">
      <h2 id="titulo-das-estrategias">Estratégias acompanhadas</h2>
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Conferindo as suas estratégias com os preços de hoje…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Conteudo dados={pedido.dados} />
      )}
    </section>
  );
}
