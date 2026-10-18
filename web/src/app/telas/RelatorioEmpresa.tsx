// Relatório da empresa no app novo: as seções que a API monta (a mesma ordem da página do Streamlit
// e do PDF). Quem não é Pro recebe as seções da base de ML trancadas (só o título e o convite): a
// tranca é do servidor, esta tela só mostra, com um único link para os Planos depois delas.
import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import type {
  ItemDoRelatorioV1,
  PontoDoRelatorioV1,
  RelatorioDaEmpresaV1,
  SecaoDoRelatorioV1,
  TabelaDoRelatorioV1,
} from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

function Item({ item }: { item: ItemDoRelatorioV1 }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">{item.nome}</span>
      <span className="numero-valor">{item.texto}</span>
      {item.comparacao ? (
        <span className="legenda-do-numero">
          Contra {item.comparacao.contra}: {item.comparacao.texto}
        </span>
      ) : null}
      {item.base ? <span className="legenda-do-numero">Base: {item.base}</span> : null}
      {item.fonte ? <span className="legenda-do-numero">Fonte: {item.fonte}</span> : null}
      {item.motivo ? <span className="legenda-do-numero">{item.motivo}</span> : null}
      {item.nota ? (
        <span className="legenda-do-numero">
          Nota: <strong>{item.nota}</strong>
          {item.nota_texto ? ` · ${item.nota_texto}` : ""}
        </span>
      ) : null}
    </div>
  );
}

// os títulos dos dois lados de "O que os dados mostram" (iguais aos de src/o_que_os_dados_mostram.py)
const LADOS: [string, string][] = [
  ["forte", "Pontos fortes nos dados"],
  ["atenção", "Pontos de atenção"],
];

function Pontos({ pontos }: { pontos: PontoDoRelatorioV1[] }) {
  return (
    <>
      {LADOS.map(([lado, titulo]) => {
        const doLado = pontos.filter((p) => p.lado === lado);
        return doLado.length > 0 ? (
          <div key={lado}>
            <h3>{titulo}</h3>
            <ul>
              {doLado.map((p) => (
                <li key={p.indicador}>
                  {p.texto} <span className="apagado">Fonte: {p.tabela}.</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null;
      })}
    </>
  );
}

function Tabela({ tabela }: { tabela: TabelaDoRelatorioV1 }) {
  return (
    <details className="tabela-do-relatorio">
      <summary>{tabela.titulo}</summary>
      <div className="tabela-rolavel">
        <table className="tabela-do-app" aria-label={tabela.titulo}>
          <thead>
            <tr>
              {tabela.colunas.map((coluna) => (
                <th key={coluna} scope="col">
                  {coluna}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tabela.linhas.map((linha, i) => (
              <tr key={i}>
                {linha.map((celula, j) => (
                  <td key={j}>{celula}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function Secao({ secao }: { secao: SecaoDoRelatorioV1 }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby={`secao-${secao.chave}`}>
      <h2 id={`secao-${secao.chave}`}>{secao.titulo}</h2>
      {secao.trancada ? (
        secao.paragrafos.map((p) => (
          <p key={p} className="erro-do-app" role="note">
            {p}
          </p>
        ))
      ) : (
        <>
          {secao.pontos && secao.pontos.length > 0 ? <Pontos pontos={secao.pontos} /> : null}
          {secao.itens.length > 0 ? (
            <div className="numeros">
              {secao.itens.map((item) => (
                <Item key={item.chave} item={item} />
              ))}
            </div>
          ) : null}
          {secao.paragrafos.map((p) => (
            <p key={p}>{p}</p>
          ))}
          {secao.tabelas.map((t) => (
            <Tabela key={t.chave} tabela={t} />
          ))}
        </>
      )}
    </section>
  );
}

function ConviteDoPro() {
  return (
    <p>
      <Link to="/planos">Conhecer o plano Pro</Link>
    </p>
  );
}

function Resultado({ relatorio }: { relatorio: RelatorioDaEmpresaV1 }) {
  return (
    <>
      <p>
        <strong>{relatorio.empresa}</strong> · {relatorio.setor || "setor não informado"} · CNPJ {relatorio.cnpj}
      </p>
      {relatorio.em_conferencia ? (
        <p className="erro-do-app" role="note">
          Há números desta empresa em conferência pelas regras de qualidade: veja a seção Qualidade dos dados.
        </p>
      ) : null}
      {relatorio.secoes.map((secao, i) => (
        <div key={secao.chave}>
          <Secao secao={secao} />
          {/* um convite depois das seções trancadas, não um por seção */}
          {secao.trancada && !relatorio.secoes[i + 1]?.trancada ? <ConviteDoPro /> : null}
        </div>
      ))}
      <p className="apagado">Fontes: {relatorio.fontes.join("; ")}. Nada aqui é recomendação.</p>
    </>
  );
}

export function RelatorioEmpresa({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<RelatorioDaEmpresaV1>
      pagina={pagina}
      carregando="Montando o relatório…"
      resultado={(relatorio) => <Resultado relatorio={relatorio} />}
    />
  );
}
