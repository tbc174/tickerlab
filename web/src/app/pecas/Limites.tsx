// Peça única: "Limites e cuidados", a seção que diz o que o dado não cobre. É obrigatória em toda tela de
// análise e nos relatórios (AGENTS.md): por isso, sem item nenhum ela não some, avisa que a API não mandou.
interface Propriedades {
  itens: string[];
  /** Duas seções de limites na mesma tela pedem ids diferentes. */
  id?: string;
}

export function Limites({ itens, id = "limites-da-tela" }: Propriedades) {
  return (
    <section className="secao-do-relatorio" aria-labelledby={id}>
      <h2 id={id}>Limites e cuidados</h2>
      {itens.length > 0 ? (
        <ul>
          {itens.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="apagado">Os limites deste dado não vieram na resposta. Leia os números com esse cuidado.</p>
      )}
    </section>
  );
}
