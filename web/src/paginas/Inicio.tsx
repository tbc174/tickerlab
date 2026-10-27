// Página inicial para quem analisa empresas (plano do site para quem analisa, 18/10/2026, PR 5): a
// assinatura, o que a base tem (números do catálogo e da medição, nunca digitados), a chamada do
// estudo do dia, a vitrine das análises abertas, os cruzamentos da base (PR 6), as quatro regras da base, as fontes com licença e
// os planos. A fita de ativos, a busca e o painel de PETR4 saíram: o público agora é quem analisa.
import { BuscaDaBase } from "../site/BuscaDaBase";
import { baseEmNumeros, catalogo } from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { Cruzamentos } from "../site/Cruzamentos";
import { AvisoDeAcesso, ChamadaFinal } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { ancora } from "../site/Leitura";
import { ASSINATURA, REGRAS_DA_BASE, linkDoApp } from "../site/textos";
import { Vitrine } from "../site/Vitrine";
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
const milhares = (n: number) => n.toLocaleString("pt-BR");

/** Os três números da abertura, cada um com a conta recolhida ao lado. */
function PainelDaBase() {
  const { totais } = catalogo;
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

export function Inicio() {
  return (
    <>
      <Heroi />
      <EstudoDoDia />
      <Vitrine />
      <Cruzamentos />
      <RegrasDaBase />
      <FontesDaBase />
      <ChamadaFinal
        titulo="Comece pelo Gratuito"
        subtitulo="O plano Gratuito não pede cartão. O que cada plano inclui está na página de planos."
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
