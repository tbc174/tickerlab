// Pacote agregado do ITBI: filtro na API, escolha do mês local e cobertura sempre visível.
import { useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { Carregando } from "../Carregando";
import { formatarData, formatarMes } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { RadarImobiliarioV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const inteiro = (n: number | null) => n === null ? "—" : n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const reais = (n: number | null) => n === null ? "—" : n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const percentual = (n: number | null) => n === null ? "—" : `${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;

function Resultado({ dados }: { dados: RadarImobiliarioV1 }) {
  const [escolhido, escolher] = useState("");
  const ponto = dados.serie.find((p) => p.mes === escolhido) ?? dados.serie.at(-1);
  if (!ponto) return <p role="status">Sem dados para este município e recorte.</p>;
  const regioes = dados.regioes.filter((r) => r.mes === ponto.mes).sort((a, b) => b.quantidade - a.quantidade || a.nome.localeCompare(b.nome));
  const nome = dados.tipo_regiao === "distrito" ? "Distritos" : "Bairros";
  return (
    <>
      <p>{dados.definicao}</p>
      <p className="apagado">Apuração: {formatarData(dados.apurado_em)} · Último mês: {formatarMes(dados.serie.at(-1)!.mes + "-01")}</p>
      <GraficoDeLinha
        titulo="Atividade imobiliária por mês (operações de ITBI)"
        datas={dados.serie.map((p) => p.mes + "-01")}
        series={[{ nome: dados.cidade === "SP" ? "DTIs pagas" : "Operações", cor: "var(--serie-1)", valores: dados.serie.map((p) => p.quantidade) }]}
        formatarValor={inteiro} formatarDia={formatarMes}
      />
      <div className="formulario-do-app"><label>Mês de referência
        <select value={ponto.mes} onChange={(e) => escolher(e.target.value)}>
          {dados.serie.map((p) => <option key={p.mes} value={p.mes}>{formatarMes(p.mes + "-01")}</option>)}
        </select>
      </label></div>
      <section aria-label="Resumo do mês" aria-live="polite">
        <div className="numeros">
          <div className="numero-do-painel"><span className="numero-rotulo">Operações</span><strong className="numero-valor">{inteiro(ponto.quantidade)}</strong></div>
          <div className="numero-do-painel"><span className="numero-rotulo">Variação anual do volume</span><strong className="numero-valor">{percentual(ponto.variacao_anual_pct)}</strong></div>
          <div className="numero-do-painel"><span className="numero-rotulo">Valor médio declarado</span><strong className="numero-valor">{reais(ponto.valor_medio)}</strong></div>
        </div>
        <p>{inteiro(ponto.localizadas)} de {inteiro(ponto.quantidade)} operações com {dados.tipo_regiao} identificado ({ponto.quantidade ? percentual(100 * ponto.localizadas / ponto.quantidade) : "—"}).</p>
        {regioes.length ? (
          <div className="tabela-rolavel">
            <table className="tabela-do-app">
              <caption>{nome} por volume · {formatarMes(ponto.mes + "-01")}</caption>
              <thead><tr><th scope="col">{dados.tipo_regiao === "distrito" ? "Distrito" : "Bairro"}</th><th scope="col">Operações</th><th scope="col">Valor médio declarado</th></tr></thead>
              <tbody>{regioes.map((r) => <tr key={r.nome}><th scope="row">{r.nome}</th><td className="numero">{inteiro(r.quantidade)}</td><td className="numero">{reais(r.valor_medio)}</td></tr>)}</tbody>
            </table>
          </div>
        ) : <p>Sem recorte territorial neste mês.</p>}
      </section>
      <details><summary>Fontes, método e limites</summary>
        <p><a href={dados.fonte} target="_blank" rel="noreferrer">Fonte oficial do ITBI</a>{dados.fonte_geografica ? <> · <a href={dados.fonte_geografica} target="_blank" rel="noreferrer">Limites territoriais do GeoSampa</a></> : null}</p>
        {dados.avisos.map((aviso) => <p key={aviso}>{aviso}</p>)}
      </details>
    </>
  );
}

export function RadarImobiliario({ pagina }: { pagina: PaginaDoApp }) {
  const [cidade, mudarCidade] = useState("SP");
  const [recorte, mudarRecorte] = useState("todos");
  const pedido = usarPedido<RadarImobiliarioV1>("/v1/radar-imobiliario", { cidade, recorte });
  return <>
    <CabecalhoDaTela pagina={pagina} />
    <div className="formulario-do-app">
      <label>Município<select value={cidade} onChange={(e) => mudarCidade(e.target.value)}><option value="SP">São Paulo</option><option value="RIO">Rio de Janeiro</option></select></label>
      <label>Uso do imóvel<select value={recorte} onChange={(e) => mudarRecorte(e.target.value)}><option value="todos">Todos os usos</option><option value="residencial">Residencial</option></select></label>
    </div>
    {pedido.estado === "carregando" ? <Carregando tipo="grafico" rotulo="Carregando radar imobiliário" /> : pedido.estado === "erro" ? <ErroDaTela erro={pedido.erro} /> : <Resultado key={`${pedido.dados.cidade}-${pedido.dados.recorte}`} dados={pedido.dados} />}
  </>;
}
