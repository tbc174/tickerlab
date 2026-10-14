// A página 404. Era `nao_encontrada()` de scripts/gerar_site.py.
import { TopoDaPagina } from "../site/Fundo";
import { linkDoApp } from "../site/textos";

export const DADOS = {
  caminho: "/404.html",
  titulo: "Página não encontrada",
  descricao: "Página não encontrada.",
};

// uma linha de preço que vai bem e despenca no fim: enfeite, não dado
const QUEDA =
  "M0,60 L80,52 L150,70 L220,48 L290,64 L340,58 L380,120 L420,110 L470,190 L520,176 L600,240";

export function NaoEncontrada() {
  return (
    <TopoDaPagina
      olho="Erro 404"
      antesDoTitulo={
        <p className="v2-quatro-zero-quatro" aria-hidden="true">
          404
        </p>
      }
      titulo="Esta página não existe"
      subtitulo="O endereço pode ter mudado. Volte para o início ou abra o app."
      classe="v2-heroi-404"
    >
      <p className="acoes">
        <a className="botao primario" href="/">
          Ir para o início
        </a>
        <a className="botao secundario" href={linkDoApp()}>
          Abrir o app
        </a>
      </p>
      <svg className="v2-queda" viewBox="0 0 600 220" preserveAspectRatio="none" aria-hidden="true">
        <path pathLength={1} d={QUEDA} />
      </svg>
    </TopoDaPagina>
  );
}
