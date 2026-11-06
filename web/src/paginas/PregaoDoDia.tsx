// O pregão do dia: o fechamento da B3 em frases, um gráfico e três tabelas. O HTML sai com o último
// pregão guardado no repositório (pregao_do_dia.json, de src/texto_do_pregao.py), montado só com as
// frases do molde aprovado; no navegador, o ferramentas.js troca pelo pregão mais novo da API
// (site/PregaoAoVivo.tsx). A página confere a impressão digital do molde e, se não for a aprovada,
// não mostra o texto.
import { pregaoDoDia } from "../conteudo";
import { CorpoDoPregao, DataDoPregao, textoAprovado, titulosDoPregao } from "../site/CorpoDoPregao";
import { PaginaDeLeitura, ancora } from "../site/Leitura";

export { dataDoPregao, textoAprovado } from "../site/CorpoDoPregao";

export const DADOS = {
  caminho: "/pregao-do-dia.html",
  titulo: "Pregão do dia",
  descricao:
    "O fechamento da B3 em números: o Ibovespa, os setores contra o índice, as maiores altas e " +
    "quedas, os juros e o dólar, com a fonte de cada um.",
  atual: "/relatorios.html",
  ferramenta: true, // o ferramentas.js busca o pregão mais novo na API
};

export const AVISO_SEM_TEXTO =
  "O texto deste pregão ainda não foi conferido. Ele aparece aqui depois da conferência.";

export function PregaoDoDia() {
  const pregao = textoAprovado(pregaoDoDia);
  const titulos = pregao ? titulosDoPregao(pregao) : [];
  return (
    <PaginaDeLeitura
      olho={DADOS.titulo}
      titulo={
        <>
          O pregão de <DataDoPregao dados={pregaoDoDia} />
        </>
      }
      subtitulo="O fechamento da B3: o que os preços fizeram no dia, sem dizer por quê."
      sumario={titulos.map((t) => ({ id: ancora(t), texto: t }))}
    >
      {pregao ? (
        <div data-corpo-do-pregao="">
          <CorpoDoPregao pregao={pregao} />
        </div>
      ) : (
        <p className="v2-aviso">{AVISO_SEM_TEXTO}</p>
      )}
      <p>
        <a href="/metodologia.html">De onde vêm os dados</a> ·{" "}
        <a href="/relatorios.html">Outros relatórios</a>
      </p>
    </PaginaDeLeitura>
  );
}
