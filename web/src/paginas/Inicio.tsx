// Página inicial para quem analisa empresas (plano do site para quem analisa, 18/10/2026, PR 5): a
// assinatura, o que a base tem (números do catálogo e da medição, nunca digitados), a chamada do
// estudo do dia, a vitrine das análises abertas, o que o app acrescenta (páginas do catálogo), o que a
// base liga pelo CNPJ, os cruzamentos da base (PR 6), as quatro regras da base, as fontes com licença, as
// últimas novidades e os planos. A pílula do herói e a faixa de novidades leem a atualização mais nova de
// src/novidades.py: nada envelhece à mão. A fita de ativos, a busca e o painel de PETR4 saíram: o público agora é quem analisa.
import { BuscaDaBase } from "../site/BuscaDaBase";
import type { Funcionalidade } from "../conteudo";
import { baseEmNumeros, catalogo, modulos, novidades } from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { Cruzamentos } from "../site/Cruzamentos";
import { AvisoDeAcesso, ChamadaFinal, linkDaFuncionalidade } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { ancora } from "../site/Leitura";
import { LigadoPeloCnpj } from "../site/LigadoPeloCnpj";
import { ASSINATURA, REGRAS_DA_BASE, URL_DA_API, linkDoApp } from "../site/textos";
import { Vitrine } from "../site/Vitrine";
import { dataPorExtenso } from "./Novidades";
import {
  DADOS as RAIO_X_DO_CHOQUE,
  MOMENTO_DO_RAIO_X,
  PDF_DO_RAIO_X,
  RAIO_X,
} from "./RaioXDoChoque";

export const DADOS = {
  caminho: "/",
  ferramenta: true,
  titulo: "TickerLab",
  descricao:
    "Coleta segura e auditável das fontes públicas brasileiras para quem analisa empresas: cada " +
    "número com data, fonte e caminho até o original.",
};

// o pedaço da assinatura em destaque no título
const DESTAQUE_DO_TITULO = "auditáveis";
const SUBTITULO =
  "Coleta segura e auditável das fontes públicas brasileiras: cada número com data, fonte e " +
  "caminho até o original.";
const SEM_RESPOSTA = "licença em consulta";
// para quem o site fala (ADR 0099): quem analisa empresas, do M&A à sala de aula
const PARA_QUEM =
  "Para M&A, crédito e FIDC, research e sala de aula: números para citar, com a fonte ao lado.";
// a atualização mais nova das Novidades: alimenta a faixa "O que entrou por último", no fim da página
const ULTIMA = novidades[0];
// as páginas do app que a inicial destaca para quem analisa; o texto de cada uma vem do catálogo
// (src/modulos.py). Backtest, carteira e calculadoras ficam fora da inicial (ADR 0099).
const PAGINAS_DO_APP_EM_DESTAQUE = ["relatorio-empresa", "busca-por-cnpj", "relatorio-do-setor"];
const milhares = (n: number) => n.toLocaleString("pt-BR");

function funcionalidadePelaPagina(pagina: string): Funcionalidade {
  for (const modulo of modulos) {
    const achada = modulo.funcionalidades.find((f) => f.pagina_do_app === pagina);
    if (achada) return achada;
  }
  throw new Error(`Página do app fora do catálogo: ${pagina}`);
}

/** Os quatro números da abertura, cada um com a conta recolhida ao lado. */
function PainelDaBase() {
  const { totais, ligado_pelo_cnpj: ligado } = catalogo;
  const { numeros, medido_em_curto } = baseEmNumeros;
  return (
    <div className="v2-painel-pilha">
      <article className="v2-painel v2-painel-base" aria-labelledby="titulo-da-base">
        <header className="v2-painel-topo">
          <span className="v2-etiqueta" id="titulo-da-base">
            O que a base tem
          </span>
          <span className="ticker">Medido em {medido_em_curto}</span>
        </header>
        <dl className="v2-base-numeros">
          <div>
            <dt>tabelas, cada uma com contrato</dt>
            <dd className="v2-numero">{milhares(totais.tabelas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  Contamos as tabelas do catálogo de contratos da base. Cada contrato diz a fonte,
                  a licença, as datas e a frequência de atualização; tabela nova entra na conta
                  sozinha.
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
          <div>
            <dt>tabelas ligadas pelo CNPJ</dt>
            <dd className="v2-numero">{milhares(ligado.tabelas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  {`Contamos as tabelas do catálogo com uma coluna de CNPJ (ou da raiz dele), mais as da rede que liga empresas, fundos e tickers. Vêm de ${ligado.orgaos} órgãos públicos.`}
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
          <div>
            <dt>fontes públicas, cada uma com a sua licença</dt>
            <dd className="v2-numero">{milhares(totais.fontes)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  {`Uma fonte é um órgão ou publicação com a licença que ela mesma publica. ${totais.fontes_em_consulta} delas ainda não responderam por escrito sobre uso comercial: até a resposta, tratamos o dado delas como não comercial.`}
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
          <div>
            <dt>companhias abertas com demonstrações</dt>
            <dd className="v2-numero">{milhares(numeros.empresas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  {`CNPJs distintos com ao menos uma demonstração financeira guardada, contados na base em ${medido_em_curto}. São ${milhares(numeros.linhas_de_demonstracoes)} linhas, cada uma com o dia em que o valor ficou público.`}
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
        </dl>
        <footer className="v2-painel-rodape">
          <span>Cada tabela com fonte, licença e data</span>
          <a className="seta" href="/dados.html">
            A base inteira
          </a>
        </footer>
      </article>
    </div>
  );
}

function Heroi() {
  const [antes, depois] = ASSINATURA.split(DESTAQUE_DO_TITULO);
  return (
    <Fundo>
      <section className="heroi faixa" aria-labelledby="titulo-heroi">
        <div className="heroi-texto">
          <a className="v2-pilula" href={RAIO_X_DO_CHOQUE.caminho}>
            <span className="v2-ponto" aria-hidden="true" />
            Novo · Raio-X do circuit breaker de 26/10
            <span className="v2-pilula-seta" aria-hidden="true">
              →
            </span>
          </a>
          <h1 id="titulo-heroi">
            {antes}
            <span className="v2-degrade">{DESTAQUE_DO_TITULO}</span>
            {depois}
          </h1>
          <p className="subtitulo">{SUBTITULO}</p>
          <p className="v2-para-quem">{PARA_QUEM}</p>
          <div className="acoes">
            <a className="botao primario" href="/dados.html">
              Ver os dados
            </a>
            <a className="botao secundario" href={linkDoApp()}>
              Abrir o app
            </a>
          </div>
          <AvisoDeAcesso />
          <div data-busca-base><BuscaDaBase /></div>
        </div>
        <PainelDaBase />
      </section>
    </Fundo>
  );
}

/** A chamada do estudo do dia, logo abaixo do herói: os números vêm do próprio estudo (dados.json). */
function EstudoDoDia() {
  return (
    <section className="faixa v2-estudo" aria-labelledby="titulo-estudo-do-dia">
      <div className="v2-estudo-texto">
        <p className="olho">
          Estudo do dia · {MOMENTO_DO_RAIO_X}
        </p>
        <h2 id="titulo-estudo-do-dia">
          <a href={RAIO_X_DO_CHOQUE.caminho}>{RAIO_X.titulo}</a>
        </h2>
        <p>
          Quem caiu mais no circuit breaker de 26/10, e por quê: beta, alta entre os turnos, dívida,
          tamanho, fundos, elétricas, bancos e a comparação com o Joesley Day.
        </p>
        <div className="acoes">
          <a className="botao primario" href={RAIO_X_DO_CHOQUE.caminho}>
            Ler o Raio-X
          </a>
          <a className="botao secundario" href={PDF_DO_RAIO_X}>
            Baixar o PDF
          </a>
        </div>
      </div>
      <dl className="v2-estudo-numeros">
        <div>
          <dt>Ibovespa no dia</dt>
          <dd className="queda">{RAIO_X.ibovespa}</dd>
        </div>
        <div>
          <dt>Mediana de {RAIO_X.empresas} empresas</dt>
          <dd className="queda">{RAIO_X.mediana}</dd>
        </div>
        <div>
          <dt>Caíram 30% ou mais</dt>
          <dd>{RAIO_X.cairam_30}</dd>
        </div>
      </dl>
    </section>
  );
}

function RegrasDaBase() {
  return (
    <section className="faixa secao v2-regras" aria-labelledby="titulo-regras">
      <p className="olho">Método</p>
      <h2 id="titulo-regras">Por que confiar num número daqui</h2>
      <p className="subtitulo">
        Quatro regras valem para toda tabela da base. Abra cada uma para ler como funciona.
      </p>
      <div className="grade v2-regras-lista">
        {REGRAS_DA_BASE.map(([titulo, texto]) => (
          <ComoFoiCalculado key={titulo} resumo={titulo}>
            <p>{texto}</p>
          </ComoFoiCalculado>
        ))}
      </div>
    </section>
  );
}

function FontesDaBase() {
  const { totais, fontes } = catalogo;
  return (
    <section className="faixa secao v2-fontes-da-base" aria-labelledby="titulo-fontes">
      <p className="olho">De onde vêm os dados</p>
      <h2 id="titulo-fontes">{`${totais.fontes} fontes públicas, cada uma com a sua licença`}</h2>
      <p className="subtitulo">
        {`${totais.fontes_em_consulta} delas ainda não responderam por escrito sobre uso comercial e levam o selo de consulta: até a resposta, tratamos o dado delas como não comercial.`}
      </p>
      <ul className="v2-lista-de-fontes">
        {fontes.map((f) => (
          <li key={f.licenca}>
            <strong>{f.orgao}</strong>
            <span>{f.tabelas === 1 ? "1 tabela" : `${f.tabelas} tabelas`}</span>
            {f.situacao === "em consulta" ? (
              <span className="selo breve">{SEM_RESPOSTA}</span>
            ) : null}
          </li>
        ))}
      </ul>
      <a className="seta" href={`/dados.html#${ancora("De onde vêm os dados")}`}>
        Cada licença, uma a uma
      </a>
    </section>
  );
}

/** O que o app acrescenta às análises abertas: três páginas do catálogo, com o texto do Python. */
function NoApp() {
  return (
    <section className="faixa secao v2-no-app" aria-labelledby="titulo-no-app">
      <p className="olho">No app, com a sua conta</p>
      <h2 id="titulo-no-app">Da análise aberta ao relatório completo</h2>
      <p className="subtitulo">
        As análises acima não pedem login. Com a conta, você escolhe a empresa ou o setor, gera o
        relatório com a fonte de cada número e guarda o PDF.
      </p>
      <div className="grade tres">
        {PAGINAS_DO_APP_EM_DESTAQUE.map(funcionalidadePelaPagina).map((f) => (
          <article key={f.nome} className="cartao">
            <h3>{f.nome}</h3>
            <p>{f.descricao}</p>
            <a className="seta" href={linkDaFuncionalidade(f)}>
              Abrir no app
            </a>
          </article>
        ))}
      </div>
      <p className="contagem v2-no-app-rodape">
        Tudo o que o app tem, módulo a módulo, está em <a href="/produto.html">Produto</a>. Para o
        seu sistema, a mesma base sai pela{" "}
        <a href={URL_DA_API} rel="noopener">
          TickerLab Data
        </a>
        , a API de dados: beta fechado, documentação aberta.
      </p>
    </section>
  );
}

/** Os três itens mais novos das Novidades: a página mostra que o produto anda, sem texto que envelhece. */
/** "Relatório do setor: escolha um setor..." → título e descrição, que vira frase (maiúscula). */
function tituloEDescricao(texto: string): [string, string] {
  const corte = texto.indexOf(": ");
  if (corte <= 0) return [texto, ""];
  const descricao = texto.slice(corte + 2);
  return [texto.slice(0, corte), descricao.charAt(0).toUpperCase() + descricao.slice(1)];
}

function UltimasNovidades() {
  const itens = ULTIMA.novidades.slice(0, 3).map(tituloEDescricao);
  return (
    <section className="faixa secao v2-ultimas" aria-labelledby="titulo-ultimas">
      <p className="olho">{`Novidades · ${dataPorExtenso(ULTIMA.data)}`}</p>
      <h2 id="titulo-ultimas">O que entrou por último</h2>
      <p className="subtitulo">
        O que mudou na última atualização. A lista completa, com as correções, fica na página de
        novidades.
      </p>
      <div className="grade tres">
        {itens.map(([titulo, texto], i) => (
          <article key={`${i}-${titulo}`} className="cartao">
            <h3>{titulo}</h3>
            <p>{texto}</p>
          </article>
        ))}
      </div>
      <a className="seta" href={`/novidades.html#${ULTIMA.data}`}>
        Todas as novidades
      </a>
    </section>
  );
}

export function Inicio() {
  return (
    <>
      <Heroi />
      <EstudoDoDia />
      <Vitrine />
      <NoApp />
      <LigadoPeloCnpj />
      <Cruzamentos />
      <RegrasDaBase />
      <FontesDaBase />
      <UltimasNovidades />
      <ChamadaFinal
        titulo="Comece pelo Gratuito"
        subtitulo={
          "O plano Gratuito não pede cartão e, até o lançamento, toda conta usa os limites do " +
          "plano mais completo. O que cada plano inclui está na página de planos."
        }
      >
        <div className="acoes">
          <a className="botao primario" href={linkDoApp()}>
            Abrir o app
          </a>
          <a className="botao secundario" href="/precos.html">
            Ver os planos
          </a>
        </div>
        <p className="v2-aviso-final">
          Os dados vêm de fontes públicas e podem ter atraso ou erros. Nada aqui é recomendação de
          investimento.
        </p>
      </ChamadaFinal>
    </>
  );
}
