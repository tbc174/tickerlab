// Planos e assinatura no app novo: o plano da conta, quanto já usou, a tabela dos planos e o botão de
// assinar o Pro ou gerenciar a assinatura no Stripe (só modo de teste, ADR 0003; só admins, ADR 0029).
// Textos e o botão vêm da API (src/planos.py e src/cobranca.acao_da_assinatura): a tela só mostra.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { conteudoDoApp, planos } from "../../conteudo";
import { ErroDaApi, pedir } from "../api";
import { useConta } from "../conta";
import { eDoStripe, navegador } from "../navegador";
import type { MeuPlanoV1 } from "../tipos";
import { ErroDaTela } from "./ErroDaTela";

const ROTA_DA_ACAO = { assinar: "/v1/pagamento-da-assinatura", gerenciar: "/v1/portal-da-assinatura" };
const NOME_DA_ACAO = { assinar: "Assinar o plano Pro", gerenciar: "Gerenciar a assinatura" };
const NAO_E_DO_STRIPE = "O endereço de pagamento não parece ser do Stripe. Nada foi aberto.";

type Pedido = { estado: "carregando" } | { estado: "pronto"; dados: MeuPlanoV1 } | { estado: "erro"; erro: ErroDaApi };

/** O botão de assinar ou gerenciar: pede o endereço à API e leva a pessoa ao Stripe. */
function BotaoDoStripe({ acao }: { acao: "assinar" | "gerenciar" }) {
  const token = useConta()?.token ?? null;
  const [indo, setIndo] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const ir = () => {
    if (token === null) return;
    setIndo(true);
    setFalha(null);
    pedir<{ url: string }>(ROTA_DA_ACAO[acao], token, {}, {})
      .then(({ url }) => {
        if (!eDoStripe(url)) throw new Error(NAO_E_DO_STRIPE);
        navegador.ir(url);
      })
      .catch((erro: unknown) => {
        setFalha(erro instanceof Error ? erro.message : String(erro));
        setIndo(false);
      });
  };
  return (
    <>
      <button type="button" className="botao primario" disabled={indo} onClick={ir}>
        {NOME_DA_ACAO[acao]}
      </button>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

/** A volta do Stripe (?assinatura=ok ou =cancelada), como no app atual. */
function VoltaDoPagamento({ atualizar }: { atualizar(): void }) {
  const [busca] = useSearchParams();
  const retorno = busca.get("assinatura");
  if (retorno === "ok") {
    return (
      <div className="aviso-do-pagamento" role="status">
        <p>{conteudoDoApp.assinatura.retorno_ok}</p>
        <button type="button" className="botao" onClick={atualizar}>
          Atualizar o meu plano
        </button>
      </div>
    );
  }
  if (retorno === "cancelada") {
    return (
      <p className="apagado" role="status">
        {conteudoDoApp.assinatura.retorno_cancelado}
      </p>
    );
  }
  return null;
}

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
      <div className="tabela-rolavel">
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
      </div>
      <p className="apagado">{dados.aviso}</p>
      {dados.texto_da_acao ? <p className="apagado">{dados.texto_da_acao}</p> : null}
      {dados.acao === "assinar" || dados.acao === "gerenciar" ? <BotaoDoStripe acao={dados.acao} /> : null}
      {dados.acao === "assinar" ? <p className="apagado">{dados.nota_do_cartao}</p> : null}
    </>
  );
}

export function Planos({ pagina }: { pagina: PaginaDoApp }) {
  const token = useConta()?.token ?? null;
  const [vez, setVez] = useState(0); // "Atualizar o meu plano" pede de novo
  const [pedido, setPedido] = useState<Pedido>({ estado: "carregando" });
  const rota = pagina.contrato?.rota ?? "";
  useEffect(() => {
    if (token === null) return;
    let valendo = true;
    setPedido({ estado: "carregando" });
    pedir<MeuPlanoV1>(rota, token)
      .then((dados) => valendo && setPedido({ estado: "pronto", dados }))
      .catch((falha: unknown) => {
        if (!valendo) return;
        const erro = falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha));
        setPedido({ estado: "erro", erro });
      });
    return () => {
      valendo = false;
    };
  }, [rota, token, vez]);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      <VoltaDoPagamento atualizar={() => setVez((v) => v + 1)} />
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
