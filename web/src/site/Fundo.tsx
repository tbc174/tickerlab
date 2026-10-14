// O topo escuro das páginas do site v2 (ADR 0065): aurora, o fundo "mercado vivo" (canvas que o
// movimento.js anima), a grade fina, o horizonte azul, o conteúdo, o botão de pausa e a linha.
// Tudo o que é enfeite fica escondido dos leitores de tela; o botão de pausa é obrigatório onde
// houver animação contínua (WCAG 2.2.2).
import type { ReactNode } from "react";
import { LinhaDoHeroi } from "./comum";

/**
 * Pausa tudo o que roda sem parar na página. No site (HTML pronto), o movimento.js troca o rótulo e
 * guarda a escolha; no app (React), quem usa passa `pausado` e `aoClicar`.
 */
export function BotaoDePausa({
  pausado = false,
  aoClicar,
}: {
  pausado?: boolean;
  aoClicar?: () => void;
}) {
  return (
    <button
      className="v2-pausa"
      type="button"
      data-pausa=""
      aria-pressed={pausado ? "true" : "false"}
      onClick={aoClicar}
    >
      <svg className="pausar" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M7 5h4v14H7zM13 5h4v14h-4z" />
      </svg>
      <svg className="retomar" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M8 5v14l11-7z" />
      </svg>
      <span>{pausado ? "Retomar animação" : "Pausar animação"}</span>
    </button>
  );
}

export function Fundo({ classe = "", children }: { classe?: string; children: ReactNode }) {
  return (
    <div className={["escura topo-da-pagina v2-heroi-fundo", classe].filter(Boolean).join(" ")}>
      <div className="v2-aurora" aria-hidden="true">
        <span />
        <span />
      </div>
      <canvas className="v2-mercado" data-fundo-mercado="" aria-hidden="true" />
      <div className="v2-grade" aria-hidden="true" />
      <div className="v2-horizonte" aria-hidden="true" />
      {children}
      <BotaoDePausa />
      <LinhaDoHeroi />
    </div>
  );
}

/** O topo das outras páginas: o mesmo fundo da inicial, mais baixo ("curto" nas de leitura). */
export function TopoDaPagina({
  olho,
  titulo,
  subtitulo,
  classe = "",
  antesDoTitulo,
  children,
}: {
  olho?: string;
  titulo: string;
  subtitulo?: string;
  classe?: string;
  antesDoTitulo?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Fundo classe={["v2-heroi-pagina", classe].filter(Boolean).join(" ")}>
      <section className="faixa secao v2-pagina-topo">
        {olho ? <p className="olho">{olho}</p> : null}
        {antesDoTitulo}
        <h1>{titulo}</h1>
        {subtitulo ? <p className="subtitulo">{subtitulo}</p> : null}
        {children}
      </section>
    </Fundo>
  );
}
