// Peça única: de onde o dado veio. `Fonte` é a linha curta embaixo de um número, de uma tabela ou de uma
// resposta ("Fonte: Receita Federal · dado de 10/2026"); `Fontes` é a seção do fim da tela, com a atribuição
// e a licença de cada fonte, como a API devolve. Todo dado na tela leva uma das duas.
interface PropriedadesDaFonte {
  /** O nome da fonte como a pessoa conhece ("Receita Federal", "CVM"). */
  nome: string;
  /** A data do dado, já escrita ("10/2026", "31/12/2025"); sem ela, a linha não inventa data. */
  data?: string | null;
}

export function Fonte({ nome, data }: PropriedadesDaFonte) {
  return (
    <p className="fonte-do-dado">
      Fonte: {nome}
      {data ? <> · dado de {data}</> : null}
    </p>
  );
}

export interface FonteDaSecao {
  fonte: string;
  atribuicao: string;
  licenca?: string;
}

interface PropriedadesDasFontes {
  fontes: FonteDaSecao[];
  /** Duas seções "Fontes" na mesma tela pedem ids diferentes. */
  id?: string;
}

export function Fontes({ fontes, id = "fontes-da-tela" }: PropriedadesDasFontes) {
  if (fontes.length === 0) return null;
  return (
    <section className="secao-do-relatorio" aria-labelledby={id}>
      <h2 id={id}>Fontes</h2>
      <ul>
        {fontes.map((fonte) => (
          <li key={fonte.fonte}>
            {fonte.atribuicao}{" "}
            <span className="apagado">
              ({fonte.fonte}
              {fonte.licenca ? `; licença: ${fonte.licenca}` : ""})
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
