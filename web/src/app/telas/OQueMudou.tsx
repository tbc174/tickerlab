// O que mudou (linha 804): o que entrou no app a cada dia, com o link para abrir a página. As linhas vêm
// da API (src/o_que_mudou.py), a mais nova primeiro; a tela só as agrupa por dia.
import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { formatarData } from "../formatar";
import type { EntregaDoDiaV1, OQueMudouV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};

/** As entregas agrupadas por dia, na ordem em que vieram (a API já manda a mais nova primeiro). */
function porDia(entregas: EntregaDoDiaV1[]): [string, EntregaDoDiaV1[]][] {
  const dias = new Map<string, EntregaDoDiaV1[]>();
  for (const entrega of entregas) dias.set(entrega.data, [...(dias.get(entrega.data) ?? []), entrega]);
  return [...dias.entries()];
}

export function OQueMudou({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<OQueMudouV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {pedido.estado === "carregando" && (
        <p className="apagado" role="status">
          Carregando…
        </p>
      )}
      {pedido.estado === "erro" && <ErroDaTela erro={pedido.erro} />}
      {pedido.estado === "pronto" && pedido.dados.entregas.length === 0 && (
        <p className="apagado">Nada novo por enquanto.</p>
      )}
      {pedido.estado === "pronto" &&
        porDia(pedido.dados.entregas).map(([data, entregas]) => (
          <section key={data} aria-label={formatarData(data)}>
            <h2>{formatarData(data)}</h2>
            <ul className="telas-do-app">
              {entregas.map((entrega) => (
                <li key={entrega.url} className="cartao">
                  <Link to={`/${entrega.url}`}>{entrega.titulo}</Link>
                  <p className="apagado">{entrega.o_que}</p>
                </li>
              ))}
            </ul>
          </section>
        ))}
    </section>
  );
}
