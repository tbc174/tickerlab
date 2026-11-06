// A sala de dados por operação (B-20, PR 5), aberta a toda conta logada: as operações da conta, e em cada
// uma os documentos, as evidências, as contradições entre documentos, o checklist do tipo da operação,
// o aviso de prazo e "Baixar a sala". A tela não calcula nem escreve regra: todo texto, rótulo, prazo
// e descrição de contradição vem da API (src/api_v1/sala_painel.py). A API só devolve a sala da própria conta.
import { type FormEvent, type ReactNode, useRef, useState } from "react";
import { ErroDaApi, baixar, mudar } from "../api";
import { Carregando } from "../Carregando";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import type {
  ContradicaoDoPainelV1,
  ItemDoPainelV1,
  OperacaoDaListaV1,
  PainelV1,
  SalaV1,
} from "../tiposDaSala";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const KB = 1024;
const MB = KB * KB;
const PRAZOS_PARA_PRORROGAR = [30, 90, 180, 365];

function tamanho(bytes: number): string {
  if (bytes >= MB) return `${(bytes / MB).toFixed(1).replace(".", ",")} MB`;
  return `${Math.max(1, Math.round(bytes / KB))} KB`;
}

function mensagem(erro: unknown): string {
  return erro instanceof ErroDaApi ? erro.message : "Não deu agora. Tente de novo em instantes.";
}

/** Roda uma ação que muda a sala: mostra o erro da API e, se deu certo, pede para recarregar. */
function useAcao(aoTerminar: () => void) {
  const token = useConta()?.token ?? null;
  const [ocupada, setOcupada] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const executar = (fazer: (token: string) => Promise<unknown>) => {
    if (token === null) return;
    setOcupada(true);
    setFalha(null);
    fazer(token)
      .then(aoTerminar)
      .catch((erro: unknown) => setFalha(mensagem(erro)))
      .finally(() => setOcupada(false));
  };
  return { ocupada, falha, executar };
}

function Falha({ texto }: { texto: string | null }) {
  return texto ? (
    <p className="erro-do-app" role="alert">
      {texto}
    </p>
  ) : null;
}

function Conceito({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <details className="conceito-da-sala">
      <summary>{titulo}</summary>
      <p>{texto}</p>
    </details>
  );
}

function Secao({ id, titulo, ajuda, children }: { id: string; titulo: string; ajuda?: ReactNode; children: ReactNode }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby={id}>
      <h2 id={id}>{titulo}</h2>
      {ajuda}
      {children}
    </section>
  );
}

// --- criar operação ---------------------------------------------------------------------------

function NovaOperacao({ sala, aoCriar }: { sala: SalaV1; aoCriar: () => void }) {
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState(sala.tipos[0]?.valor ?? "");
  const [prazo, setPrazo] = useState(sala.prazo_padrao_em_dias);
  const { ocupada, falha, executar } = useAcao(() => {
    setNome("");
    aoCriar();
  });
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    executar((token) => mudar("POST", "/v1/operacoes", token, { tipo, nome, prazo_em_dias: prazo }));
  };
  return (
    <form className="formulario-do-app" onSubmit={enviar} aria-label="Nova operação">
      <div className="campos-do-formulario">
        <label>
          <span>Nome da operação</span>
          <input value={nome} onChange={(ev) => setNome(ev.target.value)} maxLength={500} required />
        </label>
        <label>
          <span>Tipo</span>
          <select value={tipo} onChange={(ev) => setTipo(ev.target.value)}>
            {sala.tipos.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.rotulo}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Guardar por</span>
          <select value={prazo} onChange={(ev) => setPrazo(Number(ev.target.value))}>
            {sala.prazos_em_dias.map((dias) => (
              <option key={dias} value={dias}>
                {dias} dias
              </option>
            ))}
          </select>
        </label>
      </div>
      <button type="submit" className="botao primario" disabled={ocupada || nome.trim() === ""}>
        Criar operação
      </button>
      <Falha texto={falha} />
    </form>
  );
}

// --- uma operação -----------------------------------------------------------------------------

function Prazo({ operacao, aoMudar }: { operacao: OperacaoDaListaV1; aoMudar: () => void }) {
  const [dias, setDias] = useState(PRAZOS_PARA_PRORROGAR[1]);
  const { ocupada, falha, executar } = useAcao(aoMudar);
  return (
    <div className="prazo-da-sala">
      <p>
        Some em <strong>{formatarData(operacao.retencao_ate)}</strong> ({operacao.dias_ate_sumir} dias).
      </p>
      {operacao.aviso_de_prazo ? (
        <p className="erro-do-app" role="note">
          {operacao.aviso_de_prazo}
        </p>
      ) : null}
      <div className="acoes-da-sala">
        <label>
          <span className="apagado">Prorrogar por </span>
          <select value={dias} onChange={(ev) => setDias(Number(ev.target.value))}>
            {PRAZOS_PARA_PRORROGAR.map((d) => (
              <option key={d} value={d}>
                {d} dias
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="botao"
          disabled={ocupada}
          onClick={() => executar((t) => mudar("POST", `/v1/operacoes/${operacao.id}/prorrogar`, t, { dias }))}
        >
          Prorrogar
        </button>
        {operacao.situacao === "aberta" ? (
          <button
            type="button"
            className="botao"
            disabled={ocupada}
            onClick={() => executar((t) => mudar("POST", `/v1/operacoes/${operacao.id}/encerrar`, t))}
          >
            Encerrar a operação
          </button>
        ) : null}
      </div>
      <Falha texto={falha} />
    </div>
  );
}

function BaixarASala({ operacao, texto }: { operacao: OperacaoDaListaV1; texto: string }) {
  const { ocupada, falha, executar } = useAcao(() => {});
  const baixarAgora = () =>
    executar(async (token) => {
      const arquivo = await baixar(`/v1/operacoes/${operacao.id}/sala`, token);
      const endereco = URL.createObjectURL(arquivo);
      const ancora = document.createElement("a");
      ancora.href = endereco;
      ancora.download = "sala.zip";
      ancora.click();
      URL.revokeObjectURL(endereco);
    });
  return (
    <div>
      <button type="button" className="botao primario" disabled={ocupada} onClick={baixarAgora}>
        Baixar a sala
      </button>
      <p className="apagado">{texto}</p>
      <Falha texto={falha} />
    </div>
  );
}

function Documentos({ painel, aoMudar }: { painel: PainelV1; aoMudar: () => void }) {
  const campo = useRef<HTMLInputElement>(null);
  const { ocupada, falha, executar } = useAcao(() => {
    if (campo.current) campo.current.value = "";
    aoMudar();
  });
  const operacao = painel.operacao;
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    const arquivo = campo.current?.files?.[0];
    if (!arquivo) return;
    const formulario = new FormData();
    formulario.append("arquivo", arquivo);
    executar((token) => mudar("POST", `/v1/operacoes/${operacao.id}/documentos`, token, formulario));
  };
  return (
    <Secao id="documentos-da-sala" titulo={`Documentos (${painel.documentos.length})`}>
      {painel.documentos.length === 0 ? (
        <p className="apagado">Ainda não há documentos nesta operação.</p>
      ) : (
        <ul>
          {painel.documentos.map((doc) => (
            <li key={doc.id}>
              <strong>{doc.nome}</strong>
              <span className="apagado">
                {" "}
                · {doc.tipo.toUpperCase()} · {tamanho(doc.tamanho_bytes)}
                {doc.paginas ? ` · ${doc.paginas} páginas` : ""} · {doc.rotulo_da_situacao}
              </span>{" "}
              <button
                type="button"
                className="botao pequeno"
                disabled={ocupada}
                onClick={() => executar((t) => mudar("DELETE", `/v1/operacoes/${operacao.id}/documentos/${doc.id}`, t))}
              >
                Apagar
              </button>
            </li>
          ))}
        </ul>
      )}
      {operacao.situacao === "aberta" ? (
        <form className="formulario-do-app" onSubmit={enviar} aria-label="Enviar documento">
          <label>
            <span>Enviar documento (PDF, XLSX, DOCX ou CSV)</span>
            <input ref={campo} type="file" accept=".pdf,.xlsx,.docx,.csv" required />
          </label>
          <button type="submit" className="botao" disabled={ocupada}>
            Enviar
          </button>
        </form>
      ) : null}
      <Falha texto={falha} />
    </Secao>
  );
}

function Evidencias({ painel, ajuda }: { painel: PainelV1; ajuda: string }) {
  return (
    <Secao id="evidencias-da-sala" titulo={`Evidências (${painel.evidencias.length})`} ajuda={<p className="apagado">{ajuda}</p>}>
      {painel.evidencias.length === 0 ? (
        <p className="apagado">Nenhuma evidência registrada ainda.</p>
      ) : (
        <ul>
          {painel.evidencias.map((e) => (
            <li key={e.id}>
              <strong>{e.metrica}</strong> ({e.periodo}): {e.valor}
              <span className="apagado">
                {" "}
                · {e.documento}
                {e.pagina ? `, página ${e.pagina}` : ""} · {e.conferida ? "trecho conferido" : "não conferida"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Secao>
  );
}

function Contradicao({ c, operacaoId, aoMudar }: { c: ContradicaoDoPainelV1; operacaoId: string; aoMudar: () => void }) {
  const [nota, setNota] = useState(c.nota ?? "");
  const { ocupada, falha, executar } = useAcao(aoMudar);
  const marcar = (estado: "explicada" | "descartada" | "aberta") =>
    executar((t) => mudar("PATCH", `/v1/operacoes/${operacaoId}/contradicoes/${c.id}`, t, { estado, nota: nota.trim() === "" ? null : nota }));
  return (
    <li className="contradicao-da-sala">
      <p>
        <strong>{c.metrica}</strong> ({c.periodo}) · <span className="apagado">{c.rotulo_do_estado}</span>
      </p>
      <p>
        {c.documento_a}: <strong>{c.valor_a}</strong> · {c.documento_b}: <strong>{c.valor_b}</strong>
      </p>
      <label className="nota-da-sala">
        <span className="apagado">Nota (obrigatória para explicar ou descartar)</span>
        <input value={nota} onChange={(ev) => setNota(ev.target.value)} />
      </label>
      <div className="acoes-da-sala">
        <button type="button" className="botao" disabled={ocupada} onClick={() => marcar("explicada")}>
          Explicar
        </button>
        <button type="button" className="botao" disabled={ocupada} onClick={() => marcar("descartada")}>
          Descartar
        </button>
        {c.estado === "aberta" ? null : (
          <button type="button" className="botao" disabled={ocupada} onClick={() => marcar("aberta")}>
            Reabrir
          </button>
        )}
      </div>
      <Falha texto={falha} />
    </li>
  );
}

function Contradicoes({ painel, ajuda, aoMudar }: { painel: PainelV1; ajuda: string; aoMudar: () => void }) {
  return (
    <Secao id="contradicoes-da-sala" titulo={`Contradições (${painel.contradicoes.length})`} ajuda={<p className="apagado">{ajuda}</p>}>
      {painel.contradicoes.length === 0 ? (
        <p className="apagado">Nenhum par de documentos se contradiz.</p>
      ) : (
        <ul>
          {painel.contradicoes.map((c) => (
            <Contradicao key={c.id} c={c} operacaoId={painel.operacao.id} aoMudar={aoMudar} />
          ))}
        </ul>
      )}
    </Secao>
  );
}

function Item({ item, painel, aoMudar }: { item: ItemDoPainelV1; painel: PainelV1; aoMudar: () => void }) {
  const { ocupada, falha, executar } = useAcao(aoMudar);
  // "recebido" é automático (há documento ligado): a pessoa escolhe os outros estados
  const escolhas = painel.estados_do_checklist.filter((e) => e.valor !== "recebido");
  return (
    <li>
      <strong>{item.titulo}</strong>
      <span className="apagado">
        {" "}
        · {item.rotulo_do_estado}
        {item.documento ? ` · ${item.documento}` : ""}
      </span>
      <p className="apagado">{item.ajuda}</p>
      <label>
        <span className="apagado">Estado de {item.titulo}</span>
        <select
          value={item.estado === "recebido" ? "pendente" : item.estado}
          disabled={ocupada}
          onChange={(ev) =>
            executar((t) => mudar("PATCH", `/v1/operacoes/${painel.operacao.id}/checklist/${item.codigo}`, t, { estado: ev.target.value }))
          }
        >
          {escolhas.map((e) => (
            <option key={e.valor} value={e.valor}>
              {e.rotulo}
            </option>
          ))}
        </select>
      </label>
      <Falha texto={falha} />
    </li>
  );
}

function Checklist({ painel, ajuda, aoMudar }: { painel: PainelV1; ajuda: string; aoMudar: () => void }) {
  return (
    <Secao
      id="checklist-da-sala"
      titulo={`Checklist (faltam revisar ${painel.itens_a_revisar} de ${painel.checklist.length})`}
      ajuda={<p className="apagado">{ajuda}</p>}
    >
      <ul>
        {painel.checklist.map((item) => (
          <Item key={item.codigo} item={item} painel={painel} aoMudar={aoMudar} />
        ))}
      </ul>
    </Secao>
  );
}

function Operacao({ sala, id, aoMudar }: { sala: SalaV1; id: string; aoMudar: () => void }) {
  const [versao, setVersao] = useState(0);
  const pedido = usarPedido<PainelV1>(`/v1/operacoes/${id}/painel`, { versao });
  const recarregar = () => {
    setVersao((v) => v + 1);
    aoMudar();
  };
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Abrindo a operação…" />;
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  const painel = pedido.dados;
  return (
    <div className="operacao-da-sala">
      <h2>
        {painel.operacao.nome} <span className="apagado">· {painel.tipo_rotulo}</span>
      </h2>
      <Prazo operacao={painel.operacao} aoMudar={recarregar} />
      <BaixarASala operacao={painel.operacao} texto={sala.conceitos.baixar} />
      <Documentos painel={painel} aoMudar={recarregar} />
      <Evidencias painel={painel} ajuda={sala.conceitos.evidencia} />
      <Contradicoes painel={painel} ajuda={sala.conceitos.contradicao} aoMudar={recarregar} />
      <Checklist painel={painel} ajuda={sala.conceitos.checklist} aoMudar={recarregar} />
    </div>
  );
}

function Lista({ sala, aberta, abrir }: { sala: SalaV1; aberta: string | null; abrir: (id: string) => void }) {
  if (sala.operacoes.length === 0) return <p className="apagado">Você ainda não tem operações. Crie a primeira acima.</p>;
  return (
    <ul className="lista-de-operacoes">
      {sala.operacoes.map((o) => (
        <li key={o.id}>
          <button type="button" className="botao" aria-pressed={aberta === o.id} onClick={() => abrir(o.id)}>
            {o.nome}
          </button>
          <span className="apagado">
            {" "}
            · {sala.tipos.find((t) => t.valor === o.tipo)?.rotulo ?? o.tipo} · {o.documentos} documentos
            {o.contradicoes_abertas > 0 ? ` · ${o.contradicoes_abertas} contradições abertas` : ""}
            {o.situacao === "encerrada" ? " · encerrada" : ""}
          </span>
          {o.aviso_de_prazo ? <span className="selo-em-breve"> prazo perto</span> : null}
        </li>
      ))}
    </ul>
  );
}

function ConteudoDaSala() {
  const [versao, setVersao] = useState(0);
  const [aberta, setAberta] = useState<string | null>(null);
  const pedido = usarPedido<SalaV1>("/v1/sala", { versao });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Abrindo a sala…" />;
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  const sala = pedido.dados;
  const recarregar = () => setVersao((v) => v + 1);
  return (
    <>
      <p>{sala.conceitos.sala}</p>
      <Conceito titulo="Por quanto tempo a sala guarda" texto={sala.conceitos.prazo} />
      <Conceito titulo="E os dados de outras pessoas nos documentos?" texto={sala.conceitos.dados_de_terceiros} />
      <NovaOperacao sala={sala} aoCriar={recarregar} />
      <Lista sala={sala} aberta={aberta} abrir={setAberta} />
      {aberta ? <Operacao key={aberta} sala={sala} id={aberta} aoMudar={recarregar} /> : null}
    </>
  );
}

export function Sala() {
  return (
    <section>
      <header className="cabecalho-da-tela">
        <div className="cabecalho-texto">
          <p className="olho">Conta</p>
          <h1>Sala de dados</h1>
        </div>
      </header>
      <ConteudoDaSala />
    </section>
  );
}
