// Preços de referência no app novo: café (arábica e robusta), algodão e fertilizantes, o preço mensal
// do Banco Mundial e do FMI. Os textos (valor, variação, legenda, avisos) chegam prontos da API, os
// mesmos do Streamlit; aqui só se desenha (ADR 0062, Emenda 2: tela nova nasce no React).
import type { PaginaDoApp } from "../../conteudo";
import { formatarDecimal, formatarMes } from "../formatar";
import { GraficoDeLinha, type Serie } from "../graficos/GraficoDeLinha";
import type { PontoDoSpreadV1, PrecoDeReferenciaV1, PrecosDeReferenciaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};
const CHAVE_DO_ROBUSTA = "cafe-robusta"; // o spread vem logo depois dele, como no Streamlit
const NOME_DO_PINK_SHEET = "Banco Mundial (Pink Sheet)";
const NOME_DO_FMI = "FMI (PCPS)";
const MINIMO_DE_MESES_NO_GRAFICO = 2;

function seriesDoItem(item: PrecoDeReferenciaV1): Serie[] {
  const series: Serie[] = [
    { nome: NOME_DO_PINK_SHEET, cor: "var(--serie-1)", valores: item.historico.map((p) => p.bm) },
  ];
  if (item.com_fmi) {
    series.push({ nome: NOME_DO_FMI, cor: "var(--serie-2)", valores: item.historico.map((p) => p.fmi) });
  }
  return series;
}

function Item({ item }: { item: PrecoDeReferenciaV1 }) {
  const rotulo = `${item.nome} (${item.unidade})`;
  return (
    <section aria-label={rotulo} className="painel-de-numeros">
      <div className="numero-do-painel">
        <span className="numero-rotulo">{rotulo}</span>
        <span className="numero-valor">{item.texto}</span>
        {item.texto_da_variacao ? <span>{item.texto_da_variacao}</span> : null}
        <span className="legenda-do-numero">{item.legenda}</span>
      </div>
      {item.historico.length >= MINIMO_DE_MESES_NO_GRAFICO ? (
        <GraficoDeLinha
          titulo={`${rotulo}, média mensal`}
          datas={item.historico.map((p) => p.mes)}
          series={seriesDoItem(item)}
          formatarValor={formatarDecimal}
          formatarDia={formatarMes}
        />
      ) : null}
      {item.nota_das_fontes ? <p className="apagado">{item.nota_das_fontes}</p> : null}
    </section>
  );
}

function Spread({ spread, titulo, nota }: { spread: PontoDoSpreadV1[]; titulo: string; nota: string }) {
  if (spread.length < MINIMO_DE_MESES_NO_GRAFICO) return null;
  return (
    <section aria-label={titulo}>
      <h2>{titulo}</h2>
      <p className="apagado">{nota}</p>
      <GraficoDeLinha
        titulo={`${titulo} (US$/kg)`}
        datas={spread.map((p) => p.mes)}
        series={[{ nome: "Arábica menos robusta", cor: "var(--serie-1)", valores: spread.map((p) => p.valor) }]}
        formatarValor={formatarDecimal}
        formatarDia={formatarMes}
      />
    </section>
  );
}

function Resultado({ dados }: { dados: PrecosDeReferenciaV1 }) {
  return (
    <>
      <p className="aviso-do-app" role="note">
        <strong>{dados.aviso_diario}</strong>
      </p>
      {dados.itens.map((item) => (
        <div key={item.chave}>
          <Item item={item} />
          {item.chave === CHAVE_DO_ROBUSTA ? (
            <Spread spread={dados.spread} titulo={dados.titulo_do_spread} nota={dados.nota_do_spread} />
          ) : null}
        </div>
      ))}
      <p className="apagado">{dados.atribuicao}</p>
    </>
  );
}

export function PrecosDeReferencia({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<PrecosDeReferenciaV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Lendo os preços do Banco Mundial e do FMI…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Resultado dados={pedido.dados} />
      )}
    </section>
  );
}
