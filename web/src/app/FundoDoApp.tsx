// O fundo escuro do site no app, contido (ADR 0065 item 2): só no login e no início, com a aurora (só
// CSS) e sem o canvas do "mercado vivo", que é do site. O botão de pausa usa a mesma escolha guardada
// pelo site; com "reduzir movimento", o CSS para a aurora e esconde o botão.
import { type ReactNode, useState } from "react";
import { BotaoDePausa } from "../site/Fundo";

const CHAVE_DA_PAUSA = "tl-animacao-pausada"; // a mesma do movimento.js do site

function lerPausa(): boolean {
  try {
    return localStorage.getItem(CHAVE_DA_PAUSA) === "1";
  } catch {
    return false; // navegador sem localStorage (janela privada, por exemplo): começa animando
  }
}

function gravarPausa(pausado: boolean) {
  try {
    localStorage.setItem(CHAVE_DA_PAUSA, pausado ? "1" : "0");
  } catch {
    // sem localStorage a escolha vale só nesta tela
  }
}

/** `telaCheia`: o fundo ocupa a página inteira (a entrada, que não tem a moldura do app). */
export function FundoDoApp({ children, telaCheia = false }: { children: ReactNode; telaCheia?: boolean }) {
  const [pausado, setPausado] = useState(lerPausa);
  const alternar = () => {
    gravarPausa(!pausado);
    setPausado(!pausado);
  };
  const classes = ["escura v2-heroi-fundo app-fundo", telaCheia ? "app-fundo-cheio" : "", pausado ? "v2-pausado" : ""];
  return (
    <div className={classes.filter(Boolean).join(" ")}>
      <div className="v2-aurora" aria-hidden="true">
        <span />
        <span />
      </div>
      <div className="v2-grade" aria-hidden="true" />
      <div className="v2-horizonte" aria-hidden="true" />
      <div className="app-fundo-conteudo">{children}</div>
      <BotaoDePausa pausado={pausado} aoClicar={alternar} />
    </div>
  );
}
