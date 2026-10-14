// Juros e inflação no app novo: os números do Banco Central com a referência, a divulgação e a fonte
// (os textos chegam prontos da API, os mesmos do Streamlit), o histórico mês a mês e o Focus.
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { Ajuda } from "../Ajuda";
import { formatarData, formatarDecimal, formatarMes } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { ExpectativaV1, JurosEInflacaoV1, NumeroDeJurosV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const { termos, fonte_focus, nota_do_focus } = conteudoDoApp.juros;
const SEM_PARAMETROS = {};

function Numero({ numero }: { numero: NumeroDeJurosV1 }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">
        <span>{numero.nome}</span>
        <Ajuda termo={termos[numero.nome] ?? numero.nome} rotulo={numero.nome} />
      </span>
      <span className="numero-valor">{numero.texto}</span>
      <span className="legenda-do-numero">{numero.legenda}</span>
    </div>
  );
}

function Expectativas({ expectativas }: { expectativas: ExpectativaV1[] }) {
  if (expectativas.length === 0) return null;
  const pesquisa = expectativas[0].pesquisa;
  return (
    <>
      <table className="tabela-do-app">
        <caption>
          O que o mercado espera (boletim Focus) <Ajuda termo="Boletim Focus" rotulo="Boletim Focus" />
        </caption>
        <thead>
          <tr>
            <th scope="col">Indicador</th>
            <th scope="col">Ano</th>
            <th scope="col">Mediana (%)</th>
          </tr>
        </thead>
        <tbody>
          {expectativas.map((e) => (
            <tr key={`${e.indicador}-${e.ano}`}>
              <td>{e.indicador}</td>
              <td>{e.ano}</td>
              <td className="numero">{formatarDecimal(e.mediana)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {pesquisa ? (
        <p className="apagado">
          Pesquisa de {formatarData(pesquisa)} · {fonte_focus}. {nota_do_focus}
        </p>
      ) : null}
    </>
  );
}

function Resultado({ dados }: { dados: JurosEInflacaoV1 }) {
  return (
    <>
      <section aria-label="Juros e inflação agora" className="painel-de-numeros">
        <div className="numeros">
          {dados.numeros.map((n) => (
            <Numero key={n.nome} numero={n} />
          ))}
        </div>
      </section>
      {dados.avisos.map((aviso) => (
        <p key={aviso} className="apagado">
          {aviso}
        </p>
      ))}
      {dados.historico.length > 1 ? (
        <GraficoDeLinha
          titulo="Meta da Selic e IPCA em 12 meses (% ao ano)"
          datas={dados.historico.map((p) => p.mes)}
          series={[
            { nome: "Meta da Selic", cor: "var(--serie-1)", valores: dados.historico.map((p) => p.selic_meta) },
            { nome: "IPCA em 12 meses", cor: "var(--serie-2)", valores: dados.historico.map((p) => p.ipca_12_meses) },
          ]}
          formatarValor={(v) => `${formatarDecimal(v)}%`}
          formatarDia={formatarMes}
        />
      ) : null}
      <Expectativas expectativas={dados.expectativas} />
    </>
  );
}

export function JurosEInflacao({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<JurosEInflacaoV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Lendo as séries do Banco Central…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Resultado dados={pedido.dados} />
      )}
    </section>
  );
}
