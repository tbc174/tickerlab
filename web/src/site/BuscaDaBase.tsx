// A vitrine pública só pede agregados. O app completo continua no seu próprio caminho.
import { useEffect, useRef, useState, type FormEvent } from "react";
import empresas from "../../conteudo/empresas_da_base.json";
import { URL_DO_APP, linkDoApp } from "./textos";

interface Destaque { titulo: string; texto: string; fonte: string; data: string }
interface Resposta { cnpj: string; empresa: string; medido_em: string; destaques: Destaque[]; aviso: string }
const ENDERECO = `${URL_DO_APP}/api/v1/base/destaques`;
const TEMPO_LIMITE = 12_000;
const INDISPONIVEL = "A busca está indisponível agora. Você pode abrir a ficha de exemplo abaixo ou tentar novamente.";

function dataEscrita(data: string): string { return data.split("-").reverse().join("/"); }

export function BuscaDaBase() {
  const [consulta, setConsulta] = useState("");
  const [resultado, setResultado] = useState<Resposta | null>(null);
  const [mensagem, setMensagem] = useState("");
  const [buscando, setBuscando] = useState(false);
  const pedido = useRef<AbortController | null>(null);
  useEffect(() => () => pedido.current?.abort(), []);

  async function buscar(evento: FormEvent) {
    evento.preventDefault();
    pedido.current?.abort();
    const controle = new AbortController();
    pedido.current = controle;
    const prazo = setTimeout(() => controle.abort(), TEMPO_LIMITE);
    setBuscando(true); setMensagem(""); setResultado(null);
    try {
      const resposta = await fetch(`${ENDERECO}?${new URLSearchParams({ q: consulta.trim() })}`, {
        credentials: "omit", signal: controle.signal,
      });
      const corpo = await resposta.json();
      if (!resposta.ok) {
        const detalhe = typeof corpo.detail === "string" ? corpo.detail : corpo.detail?.mensagem;
        setMensagem(typeof detalhe === "string" ? detalhe : INDISPONIVEL);
      } else if (Array.isArray(corpo.destaques) && typeof corpo.cnpj === "string" && typeof corpo.medido_em === "string") {
        setResultado(corpo as Resposta);
      } else setMensagem(INDISPONIVEL);
    } catch {
      setMensagem(INDISPONIVEL);
    } finally {
      clearTimeout(prazo); setBuscando(false);
    }
  }

  return (
    <section className="busca-base" id="busca-base" aria-label="Busca aberta pela base">
      <form onSubmit={buscar}>
        <label htmlFor="consulta-da-base">CNPJ, nome ou ticker</label>
        <div className="busca-base-campos">
          <input id="consulta-da-base" value={consulta} onChange={e => setConsulta(e.target.value)}
            placeholder="Ex.: CPFL, CPFE3 ou CNPJ" maxLength={120} minLength={2} required autoComplete="off" />
          <button className="botao primario" type="submit" disabled={buscando}>{buscando ? "Buscando…" : "Buscar"}</button>
        </div>
        <p className="busca-base-limite">Companhias abertas · até três destaques com fonte e data · sem login</p>
      </form>
      {mensagem ? <p role="alert">{mensagem}</p> : null}
      <div aria-live="polite" aria-busy={buscando}>
        {resultado ? <article className="busca-base-resultado">
          <h2>{resultado.empresa}</h2>
          <p>CNPJ {resultado.cnpj} · Ficha de {dataEscrita(resultado.medido_em)}</p>
          <ul>{resultado.destaques.slice(0, 3).map(d => <li key={d.titulo}>
            <h3>{d.titulo}</h3><p>{d.texto}</p><small>Fonte: {d.fonte} · Dado de {d.data}</small>
          </li>)}</ul>
          <a className="seta" href={linkDoApp("busca-por-cnpj")}>Relatório completo no app</a>
          <p className="busca-base-limite">{resultado.aviso}</p>
        </article> : null}
      </div>
      <p className="busca-base-exemplos">Ficha aberta de exemplo: {empresas.map(e =>
        <a key={e.cnpj} href={e.link}>{e.empresa} ({e.ticker})</a>)}.</p>
    </section>
  );
}
