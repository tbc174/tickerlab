// O estado vazio padrão (ADR 0096): uma frase que diz o que falta e, se houver, o caminho para resolver.
import { Link } from "react-router";

interface Propriedades {
  frase: string;
  acao?: { texto: string; para: string };
}

export function Vazio({ frase, acao }: Propriedades) {
  return (
    <div className="vazio">
      <p>{frase}</p>
      {acao ? (
        <Link className="botao pequeno" to={acao.para}>
          {acao.texto}
        </Link>
      ) : null}
    </div>
  );
}
