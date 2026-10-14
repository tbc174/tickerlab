// Planos e assinatura no app novo: o plano da conta, quanto já usou e a tabela dos planos, com os textos
// do Streamlit (src/planos.py, pela API). Só leitura: assinar e gerenciar a assinatura continuam no app
// atual até o PR do Stripe (plano planos/2026-10-14-react-conta-e-planos.md, PR 4).
import type { PaginaDoApp } from "../../conteudo";
import { planos } from "../../conteudo";
import { linkDoApp } from "../../site/textos";
import type { MeuPlanoV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">
        <span>{rotulo}</span>
      </span>
      <span className="numero-valor">{valor}</span>
    </div>
  );
}

function Resultado({ dados }: { dados: MeuPlanoV1 }) {
  return (
    <>
      <section aria-label="Seu plano" className="painel-de-numeros">
        <div className="numeros">
          <Numero rotulo="Seu plano" valor={dados.nome_do_plano} />
          <Numero rotulo="Simulações salvas" valor={dados.simulacoes} />
          <Numero rotulo="Favoritos" valor={dados.favoritos} />
        </div>
        {dados.frase_da_assinatura ? <p className="apagado">{dados.frase_da_assinatura}</p> : null}
      </section>
      <h2>O que cada plano inclui</h2>
      <table aria-label="O que cada plano inclui" className="tabela-do-app">
        <thead>
          <tr>
            <th scope="col">Recurso</th>
            {planos.nomes.map((nome) => (
              <th key={nome} scope="col">
                {nome}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dados.tabela.map((linha) => (
            <tr key={linha.Recurso}>
              <th scope="row">{linha.Recurso}</th>
              {planos.nomes.map((nome) => (
                <td key={nome}>{linha[nome]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="apagado">{dados.aviso}</p>
      <a className="botao primario" href={linkDoApp("planos")}>
        Assinar ou gerenciar a assinatura (no app atual)
      </a>
    </>
  );
}

export function Planos({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<MeuPlanoV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Lendo o seu plano…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Resultado dados={pedido.dados} />
      )}
    </section>
  );
}
