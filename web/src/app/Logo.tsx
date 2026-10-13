import { Link } from "react-router";
import { marca } from "../conteudo";

// O símbolo vem pronto de src/marca.py (SVG com currentColor: segue o tema). É o único HTML pronto
// do app, e não vem de nenhuma pessoa nem da API (há teste que confere).
const SIMBOLO = { __html: marca.simbolo_svg };

export function Logo() {
  return (
    <Link className="marca" to="/" aria-label="TickerLab, começo do app novo">
      <span className="simbolo" dangerouslySetInnerHTML={SIMBOLO} />
      <span>
        Ticker<b>Lab</b>
      </span>
    </Link>
  );
}
