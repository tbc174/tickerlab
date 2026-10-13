// Aprender: tutorial, guia e glossário, e as calculadoras que vêm por aí. Era `aprender()`.
import { Cabecalho, ChamadaFinal, SecaoDoModulo, moduloPelaChave } from "../site/comum";

export const DADOS = {
  caminho: "/aprender.html",
  titulo: "Aprender",
  descricao: "Tutorial, guia e glossário do TickerLab, e as calculadoras que vêm por aí.",
  atual: "/aprender.html",
};

export function Aprender() {
  return (
    <>
      <Cabecalho
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
