// O corpo da página do pregão do dia: as frases, o gráfico, as tabelas, os limites e as fontes. Fica
// fora de paginas/PregaoDoDia.tsx porque o ferramentas.js também o usa (o pregão mais novo, lido da
// API no navegador) e não pode levar junto os JSONs do site (conteudo.ts).
import { GraficoDeBarras } from "../graficos/GraficoDeBarras";
import { ancora } from "./Leitura";
import { TabelaPronta, type TabelaDeTexto } from "./TabelaPronta";

/** O texto de um pregão pelo molde (`src/texto_do_pregao.py`, `texto_do_pregao`). */
export interface TextoDoPregao {
  pregao: string; // AAAA-MM-DD
  frases: { grupo: string; variante: string; texto: string }[];
  grafico: { titulo: string; barras: { nome: string; valor: number; texto: string }[] };
  tabelas: TabelaDeTexto[];
  limites: string[];
  fontes: string[];
  impressao_digital: string;
}

/** O que o Python exporta (`para_o_site`) e a API devolve: o texto e a impressão do molde aprovado. */
export interface DadosDoPregao {
  molde_aprovado: string;
  pregao: TextoDoPregao;
}

const TITULO_DO_RESUMO = "O dia em frases";
const TITULO_DOS_LIMITES = "Limites e cuidados";
const TITULO_DAS_FONTES = "Fontes";

/** "2026-10-27" → "27/10/2026" */
export function dataDoPregao(iso: string): string {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

/** O texto do pregão só se foi montado com o molde aprovado; senão, nada. */
export function textoAprovado(dados: DadosDoPregao): TextoDoPregao | null {
  return dados.pregao.impressao_digital === dados.molde_aprovado ? dados.pregao : null;
}

/** Os títulos das seções, na ordem da página (o sumário ao lado). */
export function titulosDoPregao(pregao: TextoDoPregao): string[] {
  return [TITULO_DO_RESUMO, ...pregao.tabelas.map((t) => t.titulo), TITULO_DOS_LIMITES, TITULO_DAS_FONTES];
}

export function CorpoDoPregao({ pregao }: { pregao: TextoDoPregao }) {
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

/** A data do pregão marcada para o ferramentas.js trocar pela do pregão mais novo (PregaoAoVivo.tsx). */
export function DataDoPregao({ dados }: { dados: DadosDoPregao }) {
  return (
    <span data-pregao-do-dia={dados.pregao.pregao} data-molde-aprovado={dados.molde_aprovado}>
      {dataDoPregao(dados.pregao.pregao)}
    </span>
  );
}
