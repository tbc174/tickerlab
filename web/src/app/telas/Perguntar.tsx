// Perguntar (linha 903; telas 2 e 7 do canvas): o chat de IA sobre a base do TickerLab. A pergunta vai a
// POST /v1/chat e a resposta chega em linhas (NDJSON): o texto, as consultas feitas e, no fim, o "Como
// cheguei aqui" com as fontes, que o código monta (src/chat/conversa.py), não o modelo.
//
// O estado vem de GET /v1/chat/estado: se dá para perguntar, a cota da conta e se o teto do mês pausou o
// chat (o gasto em dinheiro não vem). Com o chat desligado (`TICKERLAB_CHAT`), a tela abre e diz que ele
// ainda não foi ligado e o que vai fazer; a caixa da pergunta fica travada.
//
// Pessoa física não aparece aqui: as ferramentas do chat são as do conector, pelo caminho sem pessoa.
import { type FormEvent, useEffect, useRef, useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { ErroDaApi, pedir, pedirEmLinhas } from "../api";
import {
  type Troca,
  cnpjsDaConversa,
  comEvento,
  eventoDaLinha,
  ferramentasDaConversa,
  filtrosEmLinha,
  fontesDaConversa,
  fontesDaTroca,
  formatarDuracao,
  historicoParaEnviar,
  separarLacunas,
  trocaNova,
} from "../chat";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import { Markdown } from "../Markdown";
import { Cabecalho } from "../pecas/Cabecalho";
import { Carregando } from "../pecas/Carregando";
import { Erro } from "../pecas/Erro";
import { Fonte } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import { Selo } from "../pecas/Selo";
import type { ConsultaDoChat, EstadoDoChatV1, FonteDaConsulta } from "../tipos";
import { usarPedido } from "../usarPedido";

const SEM_PARAMETROS = {};
const ROTA_DA_PERGUNTA = "/v1/chat";
const AVISO_DA_CAIXA =
  "Resposta gerada por IA a partir da base. Confira a fonte antes de usar. Nada aqui é recomendação de investimento.";
const SEM_LACUNA = "A resposta não apontou dado que falte na base para esta pergunta.";
const PAROU_NO_MEIO = "A resposta parou no meio. Pergunte de novo.";
const NAO_CHEGOU = "A pergunta não chegou ao TickerLab. Tente de novo.";

function nomeDaFonte(fonte: FonteDaConsulta): string {
  return fonte.atribuicao ?? fonte.fonte;
}

function ComoChegueiAqui({ consultas }: { consultas: ConsultaDoChat[] }) {
  const total = consultas.reduce((soma, c) => soma + (c.duracao_ms ?? 0), 0);
  const falharam = consultas.filter((c) => !c.ok).length;
  return (
    <section className="caixa-do-chat" aria-label="Como cheguei aqui">
      <h3>Como cheguei aqui</h3>
      {consultas.length === 0 ? (
        <p className="apagado">A resposta não consultou a base.</p>
      ) : (
        <>
          <ol className="consultas-do-chat">
            {consultas.map((consulta, n) => (
              // a mesma ferramenta pode ser chamada duas vezes com os mesmos filtros: a chave é a posição
              <li key={n}>
                <span className="consulta-titulo">{consulta.titulo}</span> <code>{consulta.nome}</code>
                {consulta.ok ? null : <Selo tom="alerta">não respondeu</Selo>}
                <span className="consulta-filtros">{filtrosEmLinha(consulta.filtros)}</span>
              </li>
            ))}
          </ol>
          <p className="apagado">
            {consultas.length} {consultas.length === 1 ? "consulta" : "consultas"}
            {falharam > 0 ? ` (${falharam} sem resposta)` : ""} · {formatarDuracao(total)}
          </p>
        </>
      )}
    </section>
  );
}

function OQueABaseNaoTem({ lacunas, avisos }: { lacunas: string[]; avisos: string[] }) {
  const itens = [...lacunas, ...avisos];
  return (
    <section className="caixa-do-chat caixa-das-lacunas" aria-label="O que a base não tem">
      <h3>O que a base não tem</h3>
      {itens.length === 0 ? (
        <p className="apagado">{SEM_LACUNA}</p>
      ) : (
        <ul>
          {itens.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RespostaDaTroca({ troca }: { troca: Troca }) {
  const { corpo, lacunas } = separarLacunas(troca.texto);
  const fontes = fontesDaTroca(troca);
  const respondendo = troca.situacao === "respondendo";
  return (
    <article className="resposta-do-chat" aria-label="Resposta" aria-busy={respondendo}>
      <p className="olho">TickerLab</p>
      {corpo.length > 0 ? <Markdown blocos={corpo} /> : null}
      {respondendo ? (
        <p className="apagado" role="status">
          {troca.consultando.length > 0
            ? `Consultando a base: ${troca.consultando.at(-1)?.titulo}…`
            : "Lendo a pergunta…"}
        </p>
      ) : null}
      {troca.erro ? (
        <p className="erro-do-app" role="alert">
          {troca.erro}
        </p>
      ) : null}
      {troca.situacao === "pronta" ? (
        <>
          {fontes.map((fonte) => (
            <Fonte
              key={fonte.fonte}
              nome={nomeDaFonte(fonte)}
              data={fonte.publicado_em ? formatarData(fonte.publicado_em) : null}
            />
          ))}
          <div className="caixas-do-chat">
            <ComoChegueiAqui consultas={troca.comoChegueiAqui} />
            <OQueABaseNaoTem lacunas={lacunas} avisos={troca.avisos} />
          </div>
          {troca.avisoFinal ? <p className="fonte-do-dado">{troca.avisoFinal}</p> : null}
        </>
      ) : null}
    </article>
  );
}

function NestaConversa({ trocas, comoFunciona }: { trocas: Troca[]; comoFunciona: string }) {
  const fontes = fontesDaConversa(trocas);
  const ferramentas = ferramentasDaConversa(trocas);
  const cnpjs = cnpjsDaConversa(trocas);
  return (
    <aside className="lateral-do-chat" aria-label="Nesta conversa">
      <h2>Nesta conversa</h2>
      <section aria-labelledby="fontes-usadas">
        <h3 id="fontes-usadas">Fontes usadas</h3>
        {fontes.length === 0 ? (
          <p className="apagado">Nenhuma ainda.</p>
        ) : (
          <ul>
            {fontes.map((fonte) => (
              <li key={fonte.fonte}>
                {nomeDaFonte(fonte)}
                {fonte.publicado_em ? (
                  <span className="apagado"> · dado de {formatarData(fonte.publicado_em)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="ferramentas-chamadas">
        <h3 id="ferramentas-chamadas">Ferramentas chamadas</h3>
        {ferramentas.length === 0 ? (
          <p className="apagado">Nenhuma ainda.</p>
        ) : (
          <ul>
            {ferramentas.map((f) => (
              <li key={f.titulo}>
                {f.titulo} <span className="apagado">× {f.vezes}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {cnpjs.length > 0 ? (
        <section aria-labelledby="cnpjs-consultados">
          <h3 id="cnpjs-consultados">CNPJs consultados</h3>
          <ul>
            {cnpjs.map((cnpj) => (
              <li key={cnpj}>
                <code>{cnpj}</code>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section className="caixa-do-chat" aria-labelledby="como-funciona">
        <h3 id="como-funciona">Como o chat funciona</h3>
        <p>{comoFunciona}</p>
      </section>
    </aside>
  );
}

function CotaETeto({ estado, feitasAqui }: { estado: EstadoDoChatV1; feitasAqui: number }) {
  const hoje = Math.min(estado.perguntas_hoje + feitasAqui, estado.perguntas_por_dia);
  const noMes = Math.min(estado.perguntas_no_mes + feitasAqui, estado.perguntas_por_mes);
  return (
    <p className="cota-do-chat" aria-label="Cota e teto">
      Hoje: {hoje} de {estado.perguntas_por_dia} perguntas · No mês: {noMes} de {estado.perguntas_por_mes} · Teto
      de gasto do mês: {estado.situacao === "pausado" ? "atingido, chat pausado" : "dentro do limite"}
    </p>
  );
}

function ChatParado({ estado }: { estado: EstadoDoChatV1 }) {
  const desligado = estado.situacao === "desligado";
  return (
    <section className="caixa-do-chat chat-parado" aria-label="O chat agora">
      <div className="cabecalho-titulo">
        <h2>{desligado ? "O chat ainda não está ligado" : "Não dá para perguntar agora"}</h2>
        <Selo tom="atencao">{desligado ? "Ainda não ligado" : "Parado"}</Selo>
      </div>
      <p>{estado.mensagem}</p>
      {desligado ? (
        <>
          <p className="apagado">Perguntas que ele vai responder:</p>
          <ul>
            {estado.exemplos.map((exemplo) => (
              <li key={exemplo}>{exemplo}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function Exemplos({ exemplos, escolher }: { exemplos: string[]; escolher(texto: string): void }) {
  return (
    <section aria-label="Exemplos de pergunta" className="exemplos-do-chat">
      <p className="apagado">Comece por um exemplo:</p>
      {exemplos.map((exemplo) => (
        <button key={exemplo} type="button" className="botao pequeno" onClick={() => escolher(exemplo)}>
          {exemplo}
        </button>
      ))}
    </section>
  );
}

function Conversa({ estado, rotaDoEstado }: { estado: EstadoDoChatV1; rotaDoEstado: string }) {
  const token = useConta()?.token ?? null;
  const [trocas, setTrocas] = useState<Troca[]>([]);
  const [texto, setTexto] = useState("");
  const [feitasAqui, setFeitasAqui] = useState(0);
  // a recusa da cota (do dia ou do mês) que a pergunta ouviu: vale até a tela abrir de novo
  const [recusa, setRecusa] = useState<string | null>(null);
  const proximoId = useRef(1);
  const cancelar = useRef<AbortController | null>(null);
  useEffect(() => () => cancelar.current?.abort(), []);

  const respondendo = trocas.some((t) => t.situacao === "respondendo");
  const podePerguntar = estado.pode_perguntar && recusa === null && token !== null;
  const mudar = (id: number, como: (t: Troca) => Troca) =>
    setTrocas((todas) => todas.map((t) => (t.id === id ? como(t) : t)));

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    const pergunta = texto.trim();
    if (!pergunta || respondendo || !podePerguntar || token === null) return;
    const id = proximoId.current++;
    const historico = historicoParaEnviar(
      trocas,
      estado.perguntas_no_historico,
      estado.caracteres_da_pergunta,
      estado.caracteres_do_historico,
    );
    setTrocas((todas) => [...todas, trocaNova(id, pergunta)]);
    setTexto("");
    const controle = new AbortController();
    cancelar.current = controle;
    let contou = false;
    try {
      await pedirEmLinhas(
        ROTA_DA_PERGUNTA,
        token,
        { pergunta, historico },
        (linha) => {
          const ev = eventoDaLinha(linha);
          if (ev === null) return;
          if (!contou && ev.tipo !== "erro") {
            contou = true; // a resposta começou: a pergunta já conta na cota
            setFeitasAqui((n) => n + 1);
          }
          mudar(id, (t) => comEvento(t, ev));
        },
        controle.signal,
      );
      // a conexão fechou sem o "fim": a resposta ficou pela metade
      mudar(id, (t) => (t.situacao === "respondendo" ? comEvento(t, { tipo: "erro", mensagem: PAROU_NO_MEIO }) : t));
    } catch (falha) {
      if (controle.signal.aborted) return;
      const mensagem = falha instanceof ErroDaApi ? falha.message : NAO_CHEGOU;
      mudar(id, (t) => comEvento(t, { tipo: "erro", mensagem }));
      if (falha instanceof ErroDaApi && falha.tipo === "limite") void conferirACota(token, mensagem);
    }
  }

  // um 429 pode ser a cota (vale até amanhã ou o mês que vem) ou o limite por minuto da conta (passa
  // sozinho): só o estado do servidor diz qual, e a caixa só trava quando ele diz que não dá mais
  async function conferirACota(sessao: string, mensagem: string) {
    try {
      const agora = await pedir<EstadoDoChatV1>(rotaDoEstado, sessao, SEM_PARAMETROS);
      if (!agora.pode_perguntar) setRecusa(agora.mensagem ?? mensagem);
    } catch {
      // sem o estado (o próprio limite por minuto, a rede), a caixa fica livre: a próxima pergunta diz
    }
  }

  function novaConversa() {
    cancelar.current?.abort();
    setTrocas([]);
    setTexto("");
  }

  return (
    <>
      <Cabecalho
        olho="Chat de IA"
        titulo="Perguntar"
        descricao="Pergunte em português sobre empresas brasileiras: a resposta vem da base do TickerLab, com a fonte, a data e as consultas que foram feitas."
        acoes={
          trocas.length > 0 ? (
            <button type="button" className="botao pequeno" onClick={novaConversa}>
              Nova conversa
            </button>
          ) : null
        }
      />
      <div className="grade-do-chat">
        <div className="coluna-do-chat">
          {estado.pode_perguntar ? null : <ChatParado estado={estado} />}
          {recusa ? (
            <p className="erro-do-app" role="alert">
              {recusa}
            </p>
          ) : null}
          <ol className="trocas-do-chat" aria-label="Conversa">
            {trocas.map((troca) => (
              <li key={troca.id}>
                <p className="bolha-da-pergunta" aria-label="Sua pergunta">
                  {troca.pergunta}
                </p>
                <RespostaDaTroca troca={troca} />
              </li>
            ))}
          </ol>
          {podePerguntar && trocas.length === 0 ? <Exemplos exemplos={estado.exemplos} escolher={setTexto} /> : null}
          <form className="caixa-da-pergunta" onSubmit={enviar}>
            <label className="so-para-leitor" htmlFor="pergunta-do-chat">
              Sua pergunta
            </label>
            <textarea
              id="pergunta-do-chat"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              maxLength={estado.caracteres_da_pergunta}
              rows={2}
              placeholder="Pergunte sobre uma empresa, um setor ou um CNPJ"
              disabled={!podePerguntar}
            />
            <button type="submit" className="botao primario" disabled={!podePerguntar || respondendo || !texto.trim()}>
              {respondendo ? "Respondendo…" : "Enviar"}
            </button>
          </form>
          <CotaETeto estado={estado} feitasAqui={feitasAqui} />
          {/* depois da primeira resposta, o aviso vem embaixo de cada uma */}
          {trocas.length === 0 ? <p className="fonte-do-dado">{AVISO_DA_CAIXA}</p> : null}
        </div>
        <NestaConversa trocas={trocas} comoFunciona={estado.como_funciona} />
      </div>
      <Limites itens={estado.limites} />
    </>
  );
}

export function Perguntar({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<EstadoDoChatV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section className="tela-do-chat">
      {pedido.estado === "carregando" ? <Carregando tipo="lista" rotulo="Abrindo o chat…" /> : null}
      {pedido.estado === "erro" ? <Erro erro={pedido.erro} /> : null}
      {pedido.estado === "pronto" ? <Conversa estado={pedido.dados} rotaDoEstado={pagina.contrato?.rota ?? ""} /> : null}
    </section>
  );
}
