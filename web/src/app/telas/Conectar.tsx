// Conectar (linha 832): ligar o TickerLab ao assistente de IA e usar a CLI. O texto vem da API
// (GET /v1/conectar, src/conectar.py): endereço, passos, comandos e perguntas prontas, cada um com o botão
// de copiar. A chave que aparece é sempre o exemplo tld_...; a tela não pede nem guarda chave nenhuma.
import { useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../pecas/Cabecalho";
import type { ConectarV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { Erro } from "../pecas/Erro";

const SEM_PARAMETROS = {};

function Copiavel({ texto, rotulo }: { texto: string; rotulo: string }) {
  const [copiado, setCopiado] = useState<"sim" | "nao" | null>(null);
  async function copiar() {
    try {
      if (!navigator.clipboard) throw new Error("sem área de transferência");
      await navigator.clipboard.writeText(texto);
      setCopiado("sim");
    } catch {
      setCopiado("nao");
    }
  }
  return (
    <div>
      <pre className="codigo">{texto}</pre>
      <button type="button" onClick={copiar} aria-label={`Copiar: ${rotulo}`}>
        Copiar
      </button>
      {copiado === "sim" && <span role="status"> Copiado.</span>}
      {copiado === "nao" && <span role="status"> Não deu para copiar; selecione o texto acima.</span>}
    </div>
  );
}

function Passos({ passos }: { passos: string[] }) {
  return (
    <ol>
      {passos.map((passo) => (
        <li key={passo}>{passo}</li>
      ))}
    </ol>
  );
}

export function Conectar({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<ConectarV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {pedido.estado === "carregando" && (
        <p className="apagado" role="status">
          Carregando…
        </p>
      )}
      {pedido.estado === "erro" && <Erro erro={pedido.erro} />}
      {pedido.estado === "pronto" && (
        <>
          <section aria-label="Ligar a sua IA">
            <h2>Ligar a sua IA</h2>
            <p>Endereço do conector:</p>
            <Copiavel texto={pedido.dados.endereco_do_conector} rotulo="endereço do conector" />
            <p className="apagado">
              Chave: <code>{pedido.dados.chave_de_exemplo}</code> é só o exemplo. {pedido.dados.cuidado_com_a_chave}
            </p>
            <h3>No Claude</h3>
            <Passos passos={pedido.dados.passos_no_claude} />
            <h3>No ChatGPT</h3>
            <Passos passos={pedido.dados.passos_no_chatgpt} />
          </section>
          <section aria-label="Usar a CLI">
            <h2>Usar a CLI</h2>
            {pedido.dados.comandos_da_cli.map((item) => (
              <div key={item.titulo}>
                <h3>{item.titulo}</h3>
                <Copiavel texto={item.comando} rotulo={item.titulo} />
              </div>
            ))}
          </section>
          <section aria-label="Perguntas prontas">
            <h2>Perguntas prontas</h2>
            {pedido.dados.perguntas_prontas.map((pergunta) => (
              <Copiavel key={pergunta} texto={pergunta} rotulo="pergunta pronta" />
            ))}
          </section>
          <section aria-label="Limites">
            <h2>Limites e cuidados</h2>
            <ul>
              {pedido.dados.limites.map((limite) => (
                <li key={limite}>{limite}</li>
              ))}
            </ul>
          </section>
        </>
      )}
    </section>
  );
}
