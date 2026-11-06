// Minhas simulações no app novo (ADR 0062, tela 3; Workspace, PR 1): as simulações guardadas na conta,
// a mais nova primeiro, com quantas o plano deixa. As salvas pelo app novo reabrem aqui (o endereço vem
// da API); as salvas no app atual (carteira, Monte Carlo, backtests antigos) só reabrem lá. Apagar
// pede uma confirmação na própria linha.
import { useState } from "react";
import { Link } from "react-router";
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { linkDoClassico } from "../classico";
import { mensagemDe } from "../BaixarMeusDados";
import { pedir } from "../api";
import { useConta } from "../conta";
import type { MinhasSimulacoesV1, SimulacaoV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};
const TERMO_DA_FICHA = conteudoDoApp.backtest.ficha.termo;

/** "backtest" → "Backtest", "monte_carlo" → "Monte carlo". */
function nomeDoTipo(tipo: string): string {
  const texto = tipo.replace(/_/g, " ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function descricaoDa(s: SimulacaoV1): string {
  const partes = [nomeDoTipo(s.tipo), `criada em ${new Date(s.criada_em).toLocaleDateString("pt-BR")}`];
  if (s.dados_ate) partes.push(`dados até ${s.dados_ate}`);
  if (s.veredito) partes.push(`${TERMO_DA_FICHA} ${s.veredito}`);
  return partes.join(" · ");
}

function Lista({ inicial }: { inicial: MinhasSimulacoesV1 }) {
  const token = useConta()?.token ?? null;
  // uma fonte só: a lista começa com a resposta da API e só muda pelo apagar (como em Meus dados)
  const [dados, setDados] = useState(inicial);
  const [confirmando, setConfirmando] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const apagar = (id: string) => {
    if (token === null) return;
    setFalha(null);
    pedir<MinhasSimulacoesV1>("/v1/apagar-simulacao", token, {}, { id })
      .then(setDados)
      .catch((erro: unknown) => setFalha(mensagemDe(erro)))
      .finally(() => setConfirmando(null));
  };
  return (
    <>
      <p className="apagado">Simulações guardadas: {dados.uso}.</p>
      {dados.simulacoes.length === 0 ? (
        <p className="apagado">{dados.sem_simulacoes}</p>
      ) : (
        <ul className="links-da-conta lista-de-simulacoes" aria-label="Minhas simulações">
          {dados.simulacoes.map((s) => (
            <li key={s.id}>
              <div>
                <strong>{s.nome}</strong>
                <p className="apagado">{descricaoDa(s)}</p>
                {Object.keys(s.numeros).length > 0 ? (
                  <p className="numeros-da-simulacao">
                    {Object.entries(s.numeros)
                      .map(([nome, valor]) => `${nome}: ${valor}`)
                      .join(" · ")}
                  </p>
                ) : null}
              </div>
              <div className="acoes-da-simulacao">
                {s.endereco ? (
                  <Link className="botao pequeno" to={s.endereco}>
                    Reabrir
                  </Link>
                ) : (
                  <a className="botao pequeno" href={linkDoClassico("simulacoes")}>
                    Reabrir na versão clássica
                  </a>
                )}
                {confirmando === s.id ? (
                  <>
                    <button type="button" className="botao pequeno primario" onClick={() => apagar(s.id)}>
                      Apagar mesmo
                    </button>
                    <button type="button" className="botao pequeno" onClick={() => setConfirmando(null)}>
                      Cancelar
                    </button>
                  </>
                ) : (
                  <button type="button" className="botao pequeno" onClick={() => setConfirmando(s.id)}>
                    Apagar
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

export function Simulacoes({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<MinhasSimulacoesV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Lendo as suas simulações…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Lista inicial={pedido.dados} />
      )}
      <p className="apagado">
        Para guardar uma simulação, rode um <Link to="/backtest">backtest</Link> e clique em Salvar na minha
        conta. Carteira e Monte Carlo ainda são guardados no <a href={linkDoClassico("simulacoes")}>versão clássica</a>.
      </p>
    </section>
  );
}
