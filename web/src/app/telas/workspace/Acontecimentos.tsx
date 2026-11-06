// O cartão "Acontecimentos novos" do Workspace (Workspace, PR 3): os documentos que as empresas dos ativos
// da pessoa entregaram à CVM ou à SEC desde a última visita, na ordem de relevância que a API já manda (a
// mesma do Research). Cada um abre o documento original noutra aba; o cartão só mostra, não julga.
import { formatarData } from "../../formatar";
import type { AcontecimentoV1, PulseV1 } from "../../tipos";
import { linkSeguro } from "../LinhaDoTempo";

const NENHUM = "Nenhum acontecimento novo nas empresas dos seus ativos desde a última visita.";
const FALHOU =
  "Não deu para ler os acontecimentos agora. A visita não foi marcada: o que chegou desde a última aparecem na próxima visita.";

function Acontecimento({ a }: { a: AcontecimentoV1 }) {
  // a API já filtra o link (só https da CVM ou da SEC); o filtro aqui é a segunda trava
  const link = a.link_do_original ? linkSeguro(a.link_do_original) : null;
  return (
    <li>
      <p className="apagado">
        {a.ticker} · {a.tipo} · {formatarData(a.publicado_em)} · {a.empresa}
      </p>
      <p className="titulo-do-acontecimento">{a.titulo}</p>
      {link ? (
        <a href={link} target="_blank" rel="noopener noreferrer">
          Abrir o documento na {a.fonte}
        </a>
      ) : (
        <p className="legenda-do-numero">Na {a.fonte}, sem link para o documento.</p>
      )}
      <details className="por-que-aparece">
        <summary>Por que aparece</summary>
        <ul>
          {a.por_que_aparece.map((razao) => (
            <li key={razao}>{razao}</li>
          ))}
        </ul>
      </details>
    </li>
  );
}

function Lista({ dados }: { dados: PulseV1 }) {
  if (dados.acontecimentos === null) return <p className="aviso-do-app">{FALHOU}</p>;
  if (dados.acontecimentos.length > 0) {
    return (
      <ul className="lista-de-acontecimentos" aria-label="Acontecimentos">
        {dados.acontecimentos.map((a) => (
          <Acontecimento key={a.id} a={a} />
        ))}
      </ul>
    );
  }
  // sem ativos, a frase da API diz de onde eles vêm (sem variação, não há ativo nenhum)
  const semAtivos = dados.variacoes.length === 0 && dados.sem_variacao.length === 0;
  return <p>{semAtivos ? dados.sem_ativos : NENHUM}</p>;
}

export function AcontecimentosNovos({ dados }: { dados: PulseV1 }) {
  return (
    <section className="cartao-do-workspace" aria-labelledby="titulo-dos-acontecimentos">
      <h2 id="titulo-dos-acontecimentos">Acontecimentos novos</h2>
      <Lista dados={dados} />
    </section>
  );
}
