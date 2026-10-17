// O relatório de exemplo da base: a CPFL Energia, aberta a qualquer um. Os textos e números vêm do
// Python (amostra_relatorio.json, de src/amostra_do_relatorio.py), os mesmos do PDF: nunca à mão.
import { type TabelaDaAmostra, amostraRelatorio as amostra } from "../conteudo";
import { PaginaDeLeitura, ancora } from "../site/Leitura";

export const DADOS = {
  caminho: "/relatorio-de-exemplo.html",
  titulo: `Relatório de exemplo: ${amostra.empresa}`,
  descricao:
    `O que a base do TickerLab mostra sobre a ${amostra.empresa}: fundos com a empresa, ofertas ` +
    "do grupo, rodízio do auditor, setor regulado e negócios, cruzando a CVM e as agências.",
  atual: "/relatorio-de-exemplo.html",
};

const TITULO_DOS_DESTAQUES = "O que a base mostra";
const TITULO_DOS_LIMITES = "Limites e cuidados";
const LINHAS_A_MOSTRA = 12; // tabela maior que isso fica fechada, com o número de linhas
// uma célula que é número já escrito ("R$ 1,7 bi", "11,1%", "370"): vai à direita
const NUMERO_ESCRITO = /^(R\$ |US\$ )?[-−]?[\d.,]+( mil| mi| bi)?%?$|^—$/;

const tituloDaSecao = (chave: string) =>
  amostra.secoes.find((s) => s.chave === chave)?.titulo ?? "";

const SUMARIO = [
  { id: ancora(TITULO_DOS_DESTAQUES), texto: TITULO_DOS_DESTAQUES },
  ...amostra.secoes.map((s) => ({ id: ancora(s.titulo), texto: s.titulo })),
  { id: ancora(TITULO_DOS_LIMITES), texto: TITULO_DOS_LIMITES },
];

function Tabela({ tabela }: { tabela: TabelaDaAmostra }) {
  const numericas = tabela.colunas.map((_, i) =>
    tabela.linhas.every((linha) => NUMERO_ESCRITO.test(linha[i])),
  );
  const ultima = tabela.colunas.length - 1;
  return (
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
          {tabela.linhas.map((linha, n) => (
            <tr key={`${tabela.chave}-${n}`}>
              {linha.map((celula, i) => (
                <td key={tabela.colunas[i]} className={numericas[i] ? "v2-num" : undefined}>
                  {i === ultima && tabela.links[n] ? (
                    <a href={tabela.links[n]} rel="noopener">
                      {celula}
                    </a>
                  ) : (
                    celula
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TabelaDaSecao({ tabela }: { tabela: TabelaDaAmostra }) {
  if (tabela.linhas.length <= LINHAS_A_MOSTRA) {
    return (
      <>
        <h3>{tabela.titulo}</h3>
        <Tabela tabela={tabela} />
      </>
    );
  }
  return (
    <details className="v2-tabela-da-base">
      <summary>
        {tabela.titulo} ({tabela.linhas.length} linhas)
      </summary>
      <Tabela tabela={tabela} />
    </details>
  );
}

export function RelatorioExemplo() {
  return (
    <PaginaDeLeitura
      olho="Relatório de exemplo"
      titulo={`${amostra.empresa}: o que a base do TickerLab mostra`}
      subtitulo={
        `${amostra.razao_social} · CNPJ ${amostra.cnpj} · ${amostra.ticker} · ` +
        `${amostra.setor}. Dados da base de ${amostra.dados_de}.`
      }
      sumario={SUMARIO}
    >
      <p className="v2-aviso">{amostra.aviso}</p>
      <p className="atalhos">
        <a className="botao primario" href={amostra.pdf}>
          Baixar o PDF
        </a>{" "}
        <a className="botao secundario" href="/metodologia.html">
          De onde vêm os dados
        </a>
      </p>

      <h2 id={ancora(TITULO_DOS_DESTAQUES)}>{TITULO_DOS_DESTAQUES}</h2>
      <p>
        Cada frase junta documentos que a {amostra.empresa}, os fundos e as agências entregam em
        lugares diferentes. A conta é a mesma para todas as companhias; a fonte e a data vêm
        junto.
      </p>
      <div className="v2-destaques">
        {amostra.destaques.map((d) => (
          <article key={d.chave}>
            <h3>{d.titulo}</h3>
            <p>{d.texto}</p>
            <p className="v2-fonte">
              Fonte: {d.fonte}; dado de {d.data}.{" "}
              {d.link ? (
                <>
                  <a href={d.link} rel="noopener">
                    Documento na CVM
                  </a>
                  {" · "}
                </>
              ) : null}
              <a href={`#${ancora(tituloDaSecao(d.secao))}`}>Ver o detalhe</a>
            </p>
          </article>
        ))}
      </div>

      {amostra.secoes.map((secao) => (
        <section key={secao.chave} aria-labelledby={ancora(secao.titulo)}>
          <h2 id={ancora(secao.titulo)}>{secao.titulo}</h2>
          <dl className="v2-numeros">
            {secao.itens.map((item) => (
              <div key={item.nome}>
                <dt>{item.nome}</dt>
                <dd>
                  {item.texto}
                  {item.base ? <small>{item.base}</small> : null}
                </dd>
              </div>
            ))}
          </dl>
          {secao.paragrafos.map((p) => (
            <p key={p} className={p.startsWith("Fonte:") ? "v2-fonte" : undefined}>
              {p}
            </p>
          ))}
          {secao.tabelas.map((tabela) => (
            <TabelaDaSecao key={tabela.chave} tabela={tabela} />
          ))}
        </section>
      ))}

      <h2 id={ancora(TITULO_DOS_LIMITES)}>{TITULO_DOS_LIMITES}</h2>
      <ul>
        {amostra.limites.map((limite) => (
          <li key={limite}>{limite}</li>
        ))}
      </ul>
      <p>
        Em breve no plano Pro: este relatório para qualquer companhia aberta da B3.{" "}
        <a href="/precos.html">Ver os planos</a>
      </p>
    </PaginaDeLeitura>
  );
}
