// A consulta aberta de uma tabela da base, na página Dados (virada de 5/11/2026, fase 1, PR 3): o botão
// "Consultar" de cada linha da lista escolhe a tabela, e este painel pede à API as primeiras linhas,
// sem login nem cookie, com o total, a fonte, a licença e o dia da consulta. A tabela inteira sai pelo
// link do CSV. Sem a API (desligada ou fora do ar), o painel diz que a consulta está indisponível e o
// resto da página continua valendo. No HTML pronto do build só vai a explicação: nenhuma linha vem
// embutida, e nada aqui é recomendação de investimento.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { URL_DO_APP } from "./textos";

/** Quantas linhas o painel mostra: uma amostra, na ordem das chaves da tabela (a API aceita até 1.000). */
export const LINHAS_DA_AMOSTRA = 50;
const ENDERECO = `${URL_DO_APP}/api/v1/base/tabelas`;
const TEMPO_LIMITE = 12_000;
export const INDISPONIVEL =
  "A consulta à base está indisponível agora. Tente novamente mais tarde; a lista de tabelas acima continua valendo.";
const SEM_TABELA =
  "Escolha uma tabela na lista acima (botão “Consultar”) para ver as primeiras linhas dela aqui.";
// a API desligada responde o "Not Found" do FastAPI: para quem lê, é a consulta indisponível
const API_DESLIGADA = "Not Found";

type Celula = string | number | boolean | null | Celula[] | { [chave: string]: Celula };
interface Pagina {
  tabela: string;
  versao: string;
  fonte: string;
  orgao: string;
  licenca: string;
  total: number;
  limite: number;
  colunas: string[];
  linhas: Record<string, Celula>[];
  aviso: string;
}

/** O endereço da consulta (JSON, com a amostra) ou da exportação (CSV, a tabela inteira) de uma tabela. */
export function enderecoDaConsulta(tabela: string, cnpj: string, formato: "json" | "csv"): string {
  const parametros = new URLSearchParams();
  if (formato === "json") parametros.set("limite", String(LINHAS_DA_AMOSTRA));
  if (cnpj.trim()) parametros.set("cnpj", cnpj.trim());
  const consulta = parametros.toString();
  return `${ENDERECO}/${tabela}${formato === "csv" ? ".csv" : ""}${consulta ? `?${consulta}` : ""}`;
}

function textoDaCelula(valor: Celula | undefined): string {
  if (valor === null || valor === undefined) return "";
  if (typeof valor === "boolean") return valor ? "sim" : "não";
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}

const doisDigitos = (n: number) => String(n).padStart(2, "0");

function hojeEscrito(): string {
  const hoje = new Date();
  return `${doisDigitos(hoje.getDate())}/${doisDigitos(hoje.getMonth() + 1)}/${hoje.getFullYear()}`;
}

function ePagina(corpo: unknown): corpo is Pagina {
  const c = corpo as Partial<Pagina> | null;
  return !!c && Array.isArray(c.colunas) && Array.isArray(c.linhas) && typeof c.total === "number";
}

function detalheDaRecusa(corpo: unknown): string {
  const detalhe = (corpo as { detail?: unknown } | null)?.detail;
  return typeof detalhe === "string" && detalhe !== API_DESLIGADA ? detalhe : INDISPONIVEL;
}

export function ConsultaDaBase() {
  const [tabela, setTabela] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [pagina, setPagina] = useState<Pagina | null>(null);
  const [consultadaEm, setConsultadaEm] = useState("");
  const [mensagem, setMensagem] = useState("");
  const [buscando, setBuscando] = useState(false);
  const pedido = useRef<AbortController | null>(null);
  const cnpjDigitado = useRef("");
  const painel = useRef<HTMLElement>(null);

  useEffect(() => {
    cnpjDigitado.current = cnpj;
  }, [cnpj]);

  useEffect(() => {
    // os botões "Consultar" ficam na lista de tabelas, fora deste painel: um ouvinte na página basta
    function escolher(evento: Event) {
      const botao = (evento.target as Element | null)?.closest?.("[data-consultar]");
      const nome = botao instanceof HTMLElement ? botao.dataset.consultar : undefined;
      if (!nome) return;
      setTabela(nome);
      void pedir(nome, cnpjDigitado.current);
      painel.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
    document.addEventListener("click", escolher);
    return () => {
      document.removeEventListener("click", escolher);
      pedido.current?.abort();
    };
  }, []);

  async function pedir(nome: string, cnpjPedido: string) {
    pedido.current?.abort();
    const controle = new AbortController();
    pedido.current = controle;
    const prazo = setTimeout(() => controle.abort(), TEMPO_LIMITE);
    setBuscando(true);
    setMensagem("");
    setPagina(null);
    try {
      const resposta = await fetch(enderecoDaConsulta(nome, cnpjPedido, "json"), {
        credentials: "omit",
        signal: controle.signal,
      });
      const corpo: unknown = await resposta.json();
      if (!resposta.ok) setMensagem(detalheDaRecusa(corpo));
      else if (ePagina(corpo)) {
        setPagina(corpo);
        setConsultadaEm(hojeEscrito());
      } else setMensagem(INDISPONIVEL);
    } catch {
      // um pedido novo cancelou este: nada a dizer sobre o cancelado
      if (pedido.current === controle) setMensagem(INDISPONIVEL);
    } finally {
      clearTimeout(prazo);
      if (pedido.current === controle) setBuscando(false);
    }
  }

  function consultar(evento: FormEvent) {
    evento.preventDefault();
    if (tabela) void pedir(tabela, cnpj);
  }

  return (
    <section
      className="consulta-base"
      id="consulta-da-base"
      aria-label="Consulta aberta a uma tabela da base"
      ref={painel}
    >
      <h3>Consultar uma tabela</h3>
      <form onSubmit={consultar}>
        <p className="consulta-base-tabela">
          {tabela ? (
            <>
              Tabela <code>{tabela}</code>
            </>
          ) : (
            SEM_TABELA
          )}
        </p>
        <label htmlFor="consulta-cnpj">CNPJ (opcional)</label>
        <div className="consulta-base-campos">
          <input
            id="consulta-cnpj"
            value={cnpj}
            onChange={(e) => setCnpj(e.target.value)}
            placeholder="Ex.: 02.429.144/0001-93"
            maxLength={18}
            autoComplete="off"
          />
          <button className="botao primario" type="submit" disabled={!tabela || buscando}>
            {buscando ? "Consultando…" : "Consultar"}
          </button>
        </div>
        <p className="consulta-base-limite">
          {`As primeiras ${LINHAS_DA_AMOSTRA} linhas, na ordem das chaves da tabela · sem login · a tabela inteira sai pelo CSV`}
        </p>
      </form>
      {mensagem ? <p role="alert">{mensagem}</p> : null}
      <div aria-live="polite" aria-busy={buscando}>
        {pagina ? <Resultado pagina={pagina} cnpj={cnpj} consultadaEm={consultadaEm} /> : null}
      </div>
    </section>
  );
}

function Resultado({
  pagina,
  cnpj,
  consultadaEm,
}: {
  pagina: Pagina;
  cnpj: string;
  consultadaEm: string;
}) {
  const mostradas = pagina.linhas.length;
  const total = `${pagina.total.toLocaleString("pt-BR")} ${pagina.total === 1 ? "linha" : "linhas"}`;
  return (
    <article className="consulta-base-resultado">
      <p className="consulta-base-origem">
        <strong>{total}</strong>
        {mostradas < pagina.total ? ` · mostrando as primeiras ${mostradas}` : ""}
        {` · Fonte: ${pagina.fonte} · Licença: ${pagina.licenca} · Consulta em ${consultadaEm}`}
      </p>
      {mostradas === 0 ? (
        <p>Nenhuma linha para mostrar.</p>
      ) : (
        <div className="tabela consulta-base-linhas">
          <table>
            <thead>
              <tr>
                {pagina.colunas.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pagina.linhas.map((linha, i) => (
                <tr key={i}>
                  {pagina.colunas.map((c) => (
                    <td key={c}>{textoDaCelula(linha[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <a className="seta" href={enderecoDaConsulta(pagina.tabela, cnpj, "csv")}>
        Baixar a tabela em CSV
      </a>
      <p className="consulta-base-limite">{pagina.aviso}</p>
    </article>
  );
}
