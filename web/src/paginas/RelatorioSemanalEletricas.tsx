// O relatório de setor da semana 1: elétricas. Textos e números vêm do Python
// (relatorio_semanal_eletricas.json, de src/relatorio_semanal.py): nunca à mão.
import { relatorioSemanalEletricas as relatorio } from "../conteudo";
import { PaginaDeLeitura, ancora } from "../site/Leitura";

const CAMINHO = "/relatorio-de-setor-eletricas.html";

export const DADOS = {
  caminho: CAMINHO,
  titulo: relatorio.titulo,
  descricao:
    "Quem atende os consumidores de energia do país e quem audita as companhias abertas do setor, " +
    "com a fonte e a data de cada número e o que a base ainda não tem.",
  atual: "/relatorios.html",
};

const TITULO_DOS_DESTAQUES = "O que os dados mostram";
const TITULO_DAS_TABELAS = "Os números por companhia";
const TITULO_DO_QUE_FALTA = "O que este relatório ainda não traz";
const TITULO_DOS_LIMITES = "Limites e cuidados";
// uma célula que é número já escrito ("15.443.941", "17,6%"): vai à direita
const NUMERO_ESCRITO = /^[-−]?[\d.,]+%?$/;

const SUMARIO = [
  { id: ancora(TITULO_DOS_DESTAQUES), texto: TITULO_DOS_DESTAQUES },
  { id: ancora(TITULO_DAS_TABELAS), texto: TITULO_DAS_TABELAS },
  { id: ancora(TITULO_DO_QUE_FALTA), texto: TITULO_DO_QUE_FALTA },
  { id: ancora(TITULO_DOS_LIMITES), texto: TITULO_DOS_LIMITES },
];

export function RelatorioSemanalEletricas() {
  return (
    <PaginaDeLeitura
      olho="Relatório de setor"
      titulo={relatorio.titulo}
      subtitulo={`Companhias abertas de distribuição e geração de energia. Dados da base de ${relatorio.dados_de}.`}
      sumario={SUMARIO}
    >
      <p className="v2-aviso">{relatorio.aviso}</p>

      <h2 id={ancora(TITULO_DOS_DESTAQUES)}>{TITULO_DOS_DESTAQUES}</h2>
      <div className="v2-destaques">
        {relatorio.destaques.map((d) => (
          <article key={d.titulo}>
            <h3>{d.titulo}</h3>
            <p>{d.texto}</p>
            <p className="v2-fonte">
              Fonte: {d.fonte}; dado de {d.data}.
            </p>
          </article>
        ))}
      </div>

      <h2 id={ancora(TITULO_DAS_TABELAS)}>{TITULO_DAS_TABELAS}</h2>
      {relatorio.tabelas.map((tabela) => {
        const numericas = tabela.colunas.map((_, i) =>
          tabela.linhas.every((linha) => NUMERO_ESCRITO.test(linha[i])),
        );
        return (
          <section key={tabela.chave}>
            <h3>{tabela.titulo}</h3>
            <div className="tabela">
              <table>
                <thead>
                  <tr>
                    {tabela.colunas.map((coluna, i) => (
                      <th key={coluna} scope="col" className={numericas[i] ? "v2-num" : undefined}>
                        {coluna}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tabela.linhas.map((linha) => (
                    <tr key={`${tabela.chave}-${linha[0]}`}>
                      {linha.map((celula, i) => (
                        <td key={tabela.colunas[i]} className={numericas[i] ? "v2-num" : undefined}>
                          {celula}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      <h2 id={ancora(TITULO_DO_QUE_FALTA)}>{TITULO_DO_QUE_FALTA}</h2>
      <p>
        Números do setor que ainda não entraram aqui. Cada item diz se a base já tem o dado ou se
        falta a fonte, e de onde ele viria.
      </p>
      <ul>
        {relatorio.nao_temos.map((f) => (
          <li key={f.kpi}>
            <strong>{f.kpi}.</strong> {f.motivo} <small>Fonte: {f.fonte}.</small>
          </li>
        ))}
      </ul>

      <h2 id={ancora(TITULO_DOS_LIMITES)}>{TITULO_DOS_LIMITES}</h2>
      <ul>
        {relatorio.limites.map((limite) => (
          <li key={limite}>{limite}</li>
        ))}
      </ul>
      <p>
        <a href="/metodologia.html">De onde vêm os dados</a> ·{" "}
        <a href="/relatorio-de-exemplo.html">Relatório de exemplo de uma companhia</a>
      </p>
    </PaginaDeLeitura>
  );
}
