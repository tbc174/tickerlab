// O cartão "Variação do preço" do Workspace (Workspace, PR 3): quanto o preço de cada ativo da pessoa
// mudou desde a visita, na ordem que a API manda (pulse.ordenar_variacoes: a maior mudança primeiro, para
// cima ou para baixo). Só o número com o sinal e as datas: sem cor de "bom" ou "ruim", sem adjetivo.
import { formatarData, formatarPct } from "../../formatar";
import type { PulseV1 } from "../../tipos";

export function VariacaoDoPreco({ dados }: { dados: PulseV1 }) {
  // sem nenhum ativo guardado, o cartão dos acontecimentos já diz de onde eles vêm
  if (dados.variacoes.length === 0 && dados.sem_variacao.length === 0) return null;
  return (
    <section className="cartao-do-workspace" aria-labelledby="titulo-da-variacao">
      <h2 id="titulo-da-variacao">Variação do preço</h2>
      {dados.variacoes.length > 0 ? (
        <div className="tabela-rolavel">
          <table className="tabela-do-app">
            <caption className="apagado">Desde a sua visita</caption>
            <thead>
              <tr>
                <th scope="col">Ativo</th>
                <th scope="col">Variação</th>
                <th scope="col">Período</th>
                <th scope="col">Por que aparece</th>
              </tr>
            </thead>
            <tbody>
              {dados.variacoes.map((v) => (
                <tr key={v.ticker}>
                  <td>{v.ticker}</td>
                  <td className="numero">{formatarPct(v.variacao, true)}</td>
                  <td>{`${formatarData(v.de)} → ${formatarData(v.ate)}`}</td>
                  <td>{v.por_que_aparece.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {dados.sem_variacao.length > 0 ? (
        <p className="legenda-do-numero">Sem preço para comparar: {dados.sem_variacao.join(", ")}.</p>
      ) : null}
      <p className="legenda-do-numero">{dados.nota_da_variacao}</p>
      {dados.avisos_dos_ativos.map((aviso) => (
        <p key={aviso} className="legenda-do-numero">
          {aviso}
        </p>
      ))}
    </section>
  );
}
