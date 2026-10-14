// Aprender: tutorial, guia e glossário, e as calculadoras que vêm por aí. Era `aprender()`.
import { ChamadaFinal, SecaoDoModulo, moduloPelaChave } from "../site/comum";
import { TopoDaPagina } from "../site/Fundo";

export const DADOS = {
  caminho: "/aprender.html",
  titulo: "Aprender",
  descricao: "Tutorial, guia e glossário do TickerLab, e as calculadoras que vêm por aí.",
  atual: "/aprender.html",
};

export function Aprender() {
  return (
    <>
      <TopoDaPagina
        olho="Aprender"
        titulo="Do primeiro ativo ao primeiro relatório"
        subtitulo={
          "Cada explicação leva a uma ação no produto. As calculadoras abertas ficam aqui " +
          "também."
        }
      />
      <SecaoDoModulo modulo={moduloPelaChave("aprender")} />
      <SecaoDoModulo modulo={moduloPelaChave("ferramentas")} />
      <ChamadaFinal />
    </>
  );
}
