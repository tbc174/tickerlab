// A vitrine da página inicial: as vagas de `base/vitrine.py` (VAGAS_DA_VITRINE), na ordem do plano do
// site para quem analisa. Vaga pronta leva à página que existe; vaga em breve não tem link nem data.
import { type VagaDaVitrine, vitrine } from "../conteudo";

function Vaga({ vaga }: { vaga: VagaDaVitrine }) {
  const pronta = vaga.estado === "pronta";
  return (
    <article className={pronta ? "cartao v2-vaga" : "cartao v2-vaga breve"}>
      <p className="v2-vaga-topo">
        {pronta ? (
          <span className="selo disponivel">Aberta</span>
        ) : (
          <span className="selo breve">Em breve</span>
        )}
      </p>
      <h3>{vaga.titulo}</h3>
      <p>{vaga.para_que_serve}</p>
      {pronta && vaga.link ? (
        <a className="seta" href={vaga.link}>
          Ler a análise
        </a>
      ) : null}
    </article>
  );
}

// as prontas em cima e as em breve embaixo, cada grupo na ordem do plano
const prontasPrimeiro = [
  ...vitrine.filter((v) => v.estado === "pronta"),
  ...vitrine.filter((v) => v.estado !== "pronta"),
];

export function Vitrine() {
  return (
    <section className="faixa secao v2-vitrine" aria-labelledby="titulo-vitrine">
      <p className="olho">Vitrine</p>
      <h2 id="titulo-vitrine">Análises abertas, sem login</h2>
      <p className="subtitulo">
        Leia de graça o que a base já monta. O que ainda não está pronto aparece como em breve, sem
        data prometida.
      </p>
      <div className="grade v2-vagas">
        {prontasPrimeiro.map((vaga) => (
          <Vaga key={vaga.chave} vaga={vaga} />
        ))}
      </div>
    </section>
  );
}
