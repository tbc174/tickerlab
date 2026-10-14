// O tema do app novo: Claro, Escuro ou Automático (pelo sol), como no site. A escolha fica no
// navegador ("tema"); o script do <head> (TEMA_SALVO) aplica antes de pintar a página.
import { useState } from "react";
import { OPCOES_DO_TEMA } from "../site/tema";

interface Sol {
  temaDoMomento(agora: Date, fuso: string): string;
  fusoDoAparelho(): string;
}

function aplicar(escolha: string) {
  const raiz = document.documentElement;
  const sol = (window as unknown as { TickerLabSol?: Sol }).TickerLabSol;
  const tema =
    escolha !== "auto" ? escolha : sol ? sol.temaDoMomento(new Date(), sol.fusoDoAparelho()) : "claro";
  raiz.dataset.escolha = escolha;
  if (tema === "escuro") raiz.dataset.tema = "escuro";
  else delete raiz.dataset.tema;
  try {
    localStorage.setItem("tema", escolha);
  } catch {
    // navegador sem armazenamento: o tema vale só até fechar a página
  }
}

export function MenuDoTema() {
  const [escolha, setEscolha] = useState(() => document.documentElement.dataset.escolha ?? "auto");
  return (
    <div className="tema-escolha" role="radiogroup" aria-label="Tema">
      {OPCOES_DO_TEMA.map(([valor, nome, desenho]) => (
        <button
          key={valor}
          type="button"
          role="radio"
          aria-checked={escolha === valor}
          title={nome}
          onClick={() => {
            aplicar(valor);
            setEscolha(valor);
          }}
        >
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d={desenho} />
          </svg>
          <span className="pular-leitura">{nome}</span>
        </button>
      ))}
    </div>
  );
}
