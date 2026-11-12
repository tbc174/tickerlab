// Dados e cobertura (linha 832): o que a base serve de verdade, por tabela. Tudo vem da API
// (GET /v1/dados-e-cobertura, o catálogo público sem as colunas); a tela só agrupa por módulo e não
// escreve nenhuma cobertura à mão: o que o catálogo não declara, a tela não mostra.
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import type { DadosECoberturaV1, TabelaDaCoberturaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};

/** As tabelas agrupadas por módulo, na ordem em que vieram (a API já manda a ordem do catálogo). */
function porModulo(tabelas: TabelaDaCoberturaV1[]): [string, TabelaDaCoberturaV1[]][] {
  const grupos = new Map<string, TabelaDaCoberturaV1[]>();
  for (const tabela of tabelas) grupos.set(tabela.modulo, [...(grupos.get(tabela.modulo) ?? []), tabela]);
  return [...grupos.entries()];
}

export function DadosECobertura({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<DadosECoberturaV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {pedido.estado === "carregando" && (
        <p className="apagado" role="status">
          Carregando…
        </p>
      )}
      {pedido.estado === "erro" && <ErroDaTela erro={pedido.erro} />}
      {pedido.estado === "pronto" && pedido.dados.tabelas.length === 0 && (
        <p className="apagado">O catálogo não tem nenhuma tabela para mostrar agora.</p>
      )}
      {pedido.estado === "pronto" &&
        porModulo(pedido.dados.tabelas).map(([modulo, tabelas]) => (
          <section key={modulo} aria-label={modulo}>
            <h2>{modulo}</h2>
            <div className="tabela-rolavel">
              <table className="tabela-do-app">
                <thead>
                  <tr>
                    <th>Tabela</th>
                    <th>O que traz</th>
                    <th>Fonte</th>
                    <th>Licença</th>
                    <th>Histórico desde</th>
                    <th>Atualização</th>
                  </tr>
                </thead>
                <tbody>
                  {tabelas.map((tabela) => (
                    <tr key={tabela.tabela}>
                      <td>
                        <code>{tabela.tabela}</code>
                      </td>
                      <td>{tabela.frase}</td>
                      <td>{tabela.fonte}</td>
                      <td>
                        {tabela.orgao}: {tabela.licenca}
                      </td>
                      <td>{tabela.historico_desde}</td>
                      <td>{tabela.frequencia}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
    </section>
  );
}
