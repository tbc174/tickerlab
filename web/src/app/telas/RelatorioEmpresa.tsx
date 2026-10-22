// Relatório da empresa no app novo: as seções que a API monta (a mesma ordem da página do Streamlit
// e do PDF). Quem não é Pro recebe as seções da base de ML trancadas (só o título e o convite): a
// tranca é do servidor, esta tela só mostra, com um único link para os Planos depois delas.
import { useState } from "react";
import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { useConta } from "../conta";
import { ErroDaApi, baixar } from "../api";
import type {
  AnaliseDaEmpresaV1,
  ItemDoRelatorioV1,
  NotaDaAnaliseV1,
  ParteDaAnaliseV1,
  PontoDoRelatorioV1,
  RastroDoNumeroV1,
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
      {item.base ? (
        <span className="legenda-do-numero">Base: {item.base}</span>
      ) : null}
      {item.fonte ? (
        <span className="legenda-do-numero">Fonte: {item.fonte}</span>
      ) : null}
      {item.motivo ? (
        <span className="legenda-do-numero">{item.motivo}</span>
      ) : null}
      {item.nota ? (
        <span className="legenda-do-numero">
          Nota: <strong>{item.nota}</strong>
        </span>
      ) : null}
      {item.nota_texto ? (
        <details className="legenda-do-numero">
          <summary>Como ler a nota</summary>
          {item.nota_texto}
        </details>
      ) : null}
      {item.rastro ? <ComoFoiCalculado rastro={item.rastro} /> : null}
    </div>
  );
}

// o rastro do número em um clique (item 7 do lançamento): as linhas vêm escritas da API
function ComoFoiCalculado({ rastro }: { rastro: RastroDoNumeroV1 }) {
  return (
    <details className="legenda-do-numero">
      <summary>Como foi calculado</summary>
      <ul>
        {rastro.linhas.map((linha, i) => (
          <li key={i}>
            <strong>{linha.rotulo}:</strong> {linha.texto}
            {linha.url ? (
              <>
                {" "}
                <a href={linha.url} target="_blank" rel="noreferrer">
                  abrir o original
                </a>
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
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

export function Secao({ secao }: { secao: SecaoDoRelatorioV1 }) {
  return (
    <section
      className="secao-do-relatorio"
      aria-labelledby={`secao-${secao.chave}`}
    >
      <h2 id={`secao-${secao.chave}`}>{secao.titulo}</h2>
      {secao.trancada ? (
        secao.paragrafos.map((p) => (
          <p key={p} className="erro-do-app" role="note">
            {p}
          </p>
        ))
      ) : (
        <>
          {secao.pontos && secao.pontos.length > 0 ? (
            <Pontos pontos={secao.pontos} />
          ) : null}
          {secao.itens.length > 0 ? (
            <div className="numeros">
              {secao.itens.map((item) => (
                <Item key={item.chave} item={item} />
              ))}
            </div>
          ) : null}
          {secao.recolhida ? (
            <details>
              <summary>Ver a explicação</summary>
              {secao.paragrafos.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </details>
          ) : (
            secao.paragrafos.map((p) => <p key={p}>{p}</p>)
          )}
          {secao.tabelas.map((t) => (
            <Tabela key={t.chave} tabela={t} />
          ))}
        </>
      )}
    </section>
  );
}

// a nota aberta: o número de origem, com de quando é, de onde veio e contra o que se compara
function NotaAberta({ nota }: { nota: NotaDaAnaliseV1 }) {
  return (
    <aside id={`nota-${nota.numero}`} className="legenda-do-numero" role="note">
      <strong>
        [{nota.numero}] {nota.nome}:
      </strong>{" "}
      {nota.texto}
      {nota.medido_em ? <span> Medido em {nota.medido_em}.</span> : null}
      {nota.fonte ? <span> Fonte: {nota.fonte}.</span> : null}
      {nota.comparacao ? <span> {nota.comparacao}.</span> : null}
    </aside>
  );
}

function ParteDaAnalise({
  parte,
  notas,
}: {
  parte: ParteDaAnaliseV1;
  notas: Map<number, NotaDaAnaliseV1>;
}) {
  const [aberta, setAberta] = useState<number | null>(null);
  const notaAberta = aberta === null ? undefined : notas.get(aberta);
  return (
    <section aria-labelledby={`analise-${parte.chave}`}>
      <h3 id={`analise-${parte.chave}`}>{parte.titulo}</h3>
      {parte.paragrafos.map((paragrafo, i) => (
        <p key={i}>
          {paragrafo.rotulo ? <strong>{paragrafo.rotulo}: </strong> : null}
          {paragrafo.frases.map((frase, j) => (
            <span key={j}>
              {frase.texto}
              {frase.notas.map((numero) => (
                <button
                  key={numero}
                  type="button"
                  className="nota-da-analise"
                  aria-expanded={aberta === numero}
                  aria-controls={`nota-${numero}`}
                  aria-label={`Nota ${numero}`}
                  onClick={() => setAberta(aberta === numero ? null : numero)}
                >
                  [{numero}]
                </button>
              ))}{" "}
            </span>
          ))}
        </p>
      ))}
      {notaAberta ? <NotaAberta nota={notaAberta} /> : null}
    </section>
  );
}

function Analise({ analise }: { analise: AnaliseDaEmpresaV1 }) {
  const notas = new Map(analise.notas.map((n) => [n.numero, n]));
  return (
    <>
      <section className="secao-do-relatorio" aria-labelledby="secao-analise">
        <h2 id="secao-analise">A análise</h2>
        <p className="apagado">{analise.aviso}</p>
        {analise.motivo ? (
          <p className="erro-do-app" role="note">
            Texto de reserva por regras: {analise.motivo}.
          </p>
        ) : null}
        {analise.partes.map((parte) => (
          <ParteDaAnalise key={parte.chave} parte={parte} notas={notas} />
        ))}
      </section>
      <h2>Os dados</h2>
    </>
  );
}

export function ConviteDoPro() {
  return (
    <p>
      <Link to="/planos">Conhecer o plano Pro</Link>
    </p>
  );
}

// a última seção do 1º bloco de seções trancadas (−1 quando não há nenhuma)
export function fimDoPrimeiroBloco(secoes: SecaoDoRelatorioV1[]): number {
  const inicio = secoes.findIndex((s) => s.trancada);
  if (inicio < 0) return -1;
  const depois = secoes.findIndex((s, i) => i > inicio && !s.trancada);
  return (depois < 0 ? secoes.length : depois) - 1;
}

const DECKS: { rotulo: string; formato: "pdf" | "pptx" }[] = [
  { rotulo: "Baixar deck (PDF)", formato: "pdf" },
  { rotulo: "Baixar deck (PPT)", formato: "pptx" },
];

function BaixarDeck({ rota, ticker }: { rota: string; ticker: string }) {
  const token = useConta()?.token ?? null;
  const [baixando, setBaixando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const baixarAgora = (formato: "pdf" | "pptx") => {
    if (token === null) return;
    setBaixando(true);
    setFalha(null);
    baixar(`${rota}/apresentacao`, token, undefined, { ticker, formato })
      .then((arquivo) => {
        const endereco = URL.createObjectURL(arquivo);
        const ancora = document.createElement("a");
        ancora.href = endereco;
        ancora.download = `ficha-${ticker.replace(".SA", "")}-tickerlab.${formato}`;
        ancora.click();
        URL.revokeObjectURL(endereco);
      })
      .catch((erro: unknown) =>
        setFalha(erro instanceof ErroDaApi ? erro.message : "Não deu agora. Tente de novo em instantes."),
      )
      .finally(() => setBaixando(false));
  };
  return (
    <>
      {DECKS.map(({ rotulo, formato }) => (
        <button key={formato} type="button" className="botao" disabled={baixando} onClick={() => baixarAgora(formato)}>
          {rotulo}
        </button>
      ))}
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

function Resultado({ relatorio, rota }: { relatorio: RelatorioDaEmpresaV1; rota: string }) {
  const fimDoBloco = fimDoPrimeiroBloco(relatorio.secoes);
  return (
    <>
      <BaixarDeck rota={rota} ticker={relatorio.ticker} />
      <p>
        <strong>{relatorio.empresa}</strong> ·{" "}
        {relatorio.setor || "setor não informado"} · CNPJ {relatorio.cnpj}
      </p>
      {relatorio.em_conferencia ? (
        <p className="erro-do-app" role="note">
          Há números desta empresa em conferência pelas regras de qualidade:
          veja a seção Qualidade do lucro.
        </p>
      ) : null}
      {relatorio.analise ? <Analise analise={relatorio.analise} /> : null}
      {relatorio.secoes.map((secao, i) => (
        <div key={secao.chave}>
          <Secao secao={secao} />
          {/* um convite só, depois do 1º bloco de seções trancadas */}
          {i === fimDoBloco ? <ConviteDoPro /> : null}
        </div>
      ))}
      <p className="apagado">
        Fontes: {relatorio.fontes.join("; ")}. Nada aqui é recomendação.
      </p>
    </>
  );
}

export function RelatorioEmpresa({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<RelatorioDaEmpresaV1>
      pagina={pagina}
      carregando="Montando o relatório…"
      resultado={(relatorio) => <Resultado relatorio={relatorio} rota={pagina.contrato?.rota ?? ""} />}
    />
  );
}
