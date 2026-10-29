// O pregão do dia: o fechamento da B3 em frases, um gráfico e três tabelas. Tudo vem do Python
// (pregao_do_dia.json, de src/texto_do_pregao.py), montado só com as frases do molde aprovado; a
// página confere a impressão digital do molde e, se não for a aprovada, não mostra o texto.
import { pregaoDoDia } from "../conteudo";
import { GraficoDeBarras } from "../graficos/GraficoDeBarras";
import { PaginaDeLeitura, ancora } from "../site/Leitura";
import { TabelaPronta } from "../site/TabelaPronta";

type DadosDoPregao = typeof pregaoDoDia;
type TextoDoPregao = DadosDoPregao["pregao"];

export const DADOS = {
  caminho: "/pregao-do-dia.html",
  titulo: "Pregão do dia",
  descricao:
    "O fechamento da B3 em números: o Ibovespa, os setores contra o índice, as maiores altas e " +
    "quedas, os juros e o dólar, com a fonte de cada um.",
  atual: "/relatorios.html",
};

const TITULO_DO_RESUMO = "O dia em frases";
const TITULO_DOS_LIMITES = "Limites e cuidados";
const TITULO_DAS_FONTES = "Fontes";
export const AVISO_SEM_TEXTO =
  "O texto deste pregão ainda não foi conferido. Ele aparece aqui depois da conferência.";

/** "2026-10-27" → "27/10/2026" */
export function dataDoPregao(iso: string): string {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

/** O texto do pregão só se foi montado com o molde aprovado; senão, nada. */
export function textoAprovado(dados: DadosDoPregao): TextoDoPregao | null {
  return dados.pregao.impressao_digital === dados.molde_aprovado ? dados.pregao : null;
}

function CorpoDoPregao({ pregao }: { pregao: TextoDoPregao }) {
  const textoDaBarra = new Map(pregao.grafico.barras.map((b) => [b.valor, b.texto]));
  const [setores, ...maiores] = pregao.tabelas;
  return (
    <>
      <h2 id={ancora(TITULO_DO_RESUMO)}>{TITULO_DO_RESUMO}</h2>
      {pregao.frases.map((f) => (
        <p key={f.texto}>{f.texto}</p>
      ))}

      <TabelaPronta
        tabela={setores}
        nivel="h2"
        id={ancora(setores.titulo)}
        antes={
          <GraficoDeBarras
            titulo={pregao.grafico.titulo}
            barras={pregao.grafico.barras}
            formatarValor={(valor) => textoDaBarra.get(valor) ?? ""}
          />
        }
      />
      {maiores.map((tabela) => (
        <TabelaPronta key={tabela.chave} tabela={tabela} nivel="h2" id={ancora(tabela.titulo)} />
      ))}

      <h2 id={ancora(TITULO_DOS_LIMITES)}>{TITULO_DOS_LIMITES}</h2>
      <ul>
        {pregao.limites.map((limite) => (
          <li key={limite}>{limite}</li>
        ))}
      </ul>

      <h2 id={ancora(TITULO_DAS_FONTES)}>{TITULO_DAS_FONTES}</h2>
      <ul>
        {pregao.fontes.map((fonte) => (
          <li key={fonte}>{fonte}.</li>
        ))}
      </ul>
    </>
  );
}

export function PregaoDoDia() {
  const pregao = textoAprovado(pregaoDoDia);
  const titulos = pregao
    ? [TITULO_DO_RESUMO, ...pregao.tabelas.map((t) => t.titulo), TITULO_DOS_LIMITES, TITULO_DAS_FONTES]
    : [];
  return (
    <PaginaDeLeitura
      olho={DADOS.titulo}
      titulo={`O pregão de ${dataDoPregao(pregaoDoDia.pregao.pregao)}`}
      subtitulo="O fechamento da B3: o que os preços fizeram no dia, sem dizer por quê."
      sumario={titulos.map((t) => ({ id: ancora(t), texto: t }))}
    >
      {pregao ? <CorpoDoPregao pregao={pregao} /> : <p className="v2-aviso">{AVISO_SEM_TEXTO}</p>}
      <p>
        <a href="/metodologia.html">De onde vêm os dados</a> ·{" "}
        <a href="/relatorios.html">Outros relatórios</a>
      </p>
    </PaginaDeLeitura>
  );
}
