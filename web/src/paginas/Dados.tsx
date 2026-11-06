// Dados: a base que alimenta o TickerLab, gerada do catálogo de contratos (base/contratos/catalogo.json).
// Nenhum número é digitado aqui: tabelas, fontes e módulos vêm de `catalogo` (ADRs 0048, 0065 e 0099).
// A comparação com qualquer outra base é só pelo rigor: linhagem, "como era na data", licença por
// tabela e explicação recolhida. Nada aqui é recomendação de investimento.
import {
  type FamiliaDeFonte,
  type FonteDaBase,
  type RegistroDeFonte,
  type TabelaDaBase,
  baseEmNumeros,
  catalogo,
} from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { ConsultaDaBase, enderecoDaConsulta } from "../site/ConsultaDaBase";
import { PaginaDeLeitura, ancora } from "../site/Leitura";
import { REGRAS_DA_BASE } from "../site/textos";

export const DADOS = {
  caminho: "/dados.html",
  titulo: "Dados",
  descricao:
    "A base do TickerLab: cada tabela com a fonte, a licença e a data em que o dado ficou público, " +
    "para quem analisa empresas no Brasil.",
  atual: "/dados.html",
  ferramenta: true, // o ferramentas.js liga o painel de consulta (site/ConsultaDaBase.tsx)
};

const SECOES = [
  "A base em uma linha",
  "Quatro regras que valem para toda tabela",
  "O que há na base",
  "De onde vêm os dados",
  "Todas as fontes que temos, uma a uma",
  "O que ainda não está na base",
  "Como auditar um número",
];

const MARCAS: Record<RegistroDeFonte["marca"], string> = {
  vendavel: "Pode ser repassada, citando a fonte",
  uso_interno: "Só uso interno",
  nao_comercial: "Não comercial",
  a_confirmar: "A confirmar",
};

const RITMOS: Record<RegistroDeFonte["ritmo"], string> = {
  diaria: "Diária",
  semanal: "Semanal",
  mensal: "Mensal",
  "carga-unica": "Carga única",
};

const SEM_RESPOSTA = "licença em consulta";
// tabela que a consulta aberta ainda não serve (fora da porta ou conferida no repositório)
const SEM_CONSULTA = "Ainda sem consulta aberta: esta tabela aparece pela ficha no app.";
// a coluna, a frase e o painel da consulta nascem escondidos e só aparecem quando a API responde
// (`mostrarSeAConsultaResponde`, ligada pelo ferramentas.js): sem ela, a página não promete a consulta
const COM_CONSULTA = { "data-com-consulta": "", hidden: true } as const;
const FRASE_DA_CONSULTA =
  '"Consulta" mostra as primeiras linhas da tabela aqui mesmo, sem login; "CSV" baixa a mesma consulta, ' +
  "cada linha com a fonte, a licença e o dia em que ficou pública, até o teto de linhas da API (o painel " +
  "mostra quanto); se a tabela tiver mais, a última linha do arquivo avisa.";

function dataPorExtenso(iso: string): string {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

function SeloDeConsulta() {
  return <span className="selo breve">{SEM_RESPOSTA}</span>;
}

function LinhaDaTabela({ t }: { t: TabelaDaBase }) {
  return (
    <tr data-tabela={`${t.tabela} ${t.orgao}`.toLowerCase()}>
      <td>
        <code>{t.tabela}</code>
        <br />
        <span className="dados-frase">{t.frase}</span>
      </td>
      <td>
        {t.orgao}
        {t.situacao === "em consulta" ? (
          <>
            <br />
            <SeloDeConsulta />
          </>
        ) : null}
      </td>
      <td>
        {t.frequencia}
        {t.atraso ? (
          <>
            <br />
            <span className="dados-frase">{t.atraso}</span>
          </>
        ) : null}
      </td>
      <td>{dataPorExtenso(t.historico_desde)}</td>
      <td className="dados-consulta" {...COM_CONSULTA}>
        {t.consultavel ? (
          <>
            <button type="button" className="dados-consultar" data-consultar={t.tabela}>
              Consultar
            </button>{" "}
            <a href={enderecoDaConsulta(t.tabela, "", "csv")}>CSV</a>
          </>
        ) : (
          <span className="dados-frase" title={SEM_CONSULTA}>
            só no app
          </span>
        )}
      </td>
    </tr>
  );
}

function TabelasDoModulo({ chave, nome }: { chave: string; nome: string }) {
  const tabelas = catalogo.tabelas.filter((t) => t.modulo === chave);
  return (
    <div className="dados-modulo" data-modulo-da-lista="">
      <h3>
        {nome} <span className="dados-contagem">{`${tabelas.length} tabelas`}</span>
      </h3>
      <div className="tabela">
        <table>
          <thead>
            <tr>
              <th>Tabela</th>
              <th>Fonte</th>
              <th>Atualização</th>
              <th>Desde</th>
              <th {...COM_CONSULTA}>Consulta</th>
            </tr>
          </thead>
          <tbody>
            {tabelas.map((t) => (
              <LinhaDaTabela key={t.tabela} t={t} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CartaoDaFonte({ f }: { f: FonteDaBase }) {
  const nomes = f.modulos.map((m) => catalogo.modulos.find((x) => x.chave === m)?.nome ?? m);
  return (
    <article className="cartao dados-fonte">
      <h3>
        {f.orgao}
        {f.situacao === "em consulta" ? <SeloDeConsulta /> : null}
      </h3>
      <p>{`${f.licenca}.`}</p>
      <p className="dados-repasse">{f.repasse}</p>
      <p className="dados-frase">
        {`${f.tabelas} ${f.tabelas === 1 ? "tabela" : "tabelas"} · ${nomes.join(", ")} · desde ${dataPorExtenso(f.historico_desde)}`}
      </p>
    </article>
  );
}

const USOS: Record<FamiliaDeFonte["uso"], string> = {
  em_uso: "Em uso",
  guardada: "Guardada",
};

const FILTROS_DE_USO: [string, string][] = [
  ["todas", "Todas"],
  ["em_uso", "Em uso"],
  ["guardada", "Guardadas"],
];

const ritmoDaColeta = new Map(catalogo.registro_de_fontes.map((r) => [r.id, RITMOS[r.ritmo]]));

/** Em uso primeiro; dentro de cada grupo, pelo nome do órgão. */
function naOrdemDaPagina(familias: FamiliaDeFonte[]): FamiliaDeFonte[] {
  return [...familias].sort(
    (a, b) =>
      Number(a.uso !== "em_uso") - Number(b.uso !== "em_uso") ||
      a.orgao.localeCompare(b.orgao, "pt-BR"),
  );
}

function ColetasDaFamilia({ f }: { f: FamiliaDeFonte }) {
  if (f.coletas.length === 0) {
    return <span className="dados-frase">Lida direto da fonte, fora do acervo</span>;
  }
  const rotulo = f.coletas.length === 1 ? "ver a coleta" : `ver as ${f.coletas.length} coletas`;
  return (
    <details className="dados-coletas">
      <summary>{rotulo}</summary>
      <ul>
        {f.coletas.map((id) => (
          <li key={id}>
            <code>{id}</code> <span className="dados-frase">{ritmoDaColeta.get(id)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function LinhaDaFamilia({ f }: { f: FamiliaDeFonte }) {
  return (
    <tr data-uso-da-fonte={f.uso}>
      <td>
        {f.link ? (
          <a href={f.link} rel="noopener" target="_blank">
            {f.orgao}
          </a>
        ) : (
          f.orgao
        )}
        <br />
        <ColetasDaFamilia f={f} />
      </td>
      <td>{USOS[f.uso]}</td>
      <td>{MARCAS[f.marca]}</td>
      <td>
        {f.licencas.map((l) => (
          <span key={l} className="dados-licenca">
            {l}
          </span>
        ))}
      </td>
      <td>{f.termos_lidos_em ? dataPorExtenso(f.termos_lidos_em) : "Termos ainda não lidos"}</td>
    </tr>
  );
}

const milhares = (n: number) => n.toLocaleString("pt-BR");

/** Os números da base, medidos de verdade e com a data da medição ao lado. */
function NumerosDaBase() {
  const { numeros: n, medido_em_curto } = baseEmNumeros;
  const itens: [number, string][] = [
    [n.empresas, "companhias com demonstrações"],
    [n.linhas_de_demonstracoes, "linhas de demonstrações"],
    [n.versoes, "linhas reapresentadas (versão 2 em diante)"],
    [n.eventos, "eventos e comunicados"],
    [n.originais_com_hash, "arquivos originais com SHA-256 guardado"],
  ];
  return (
    <>
      <dl className="grade dados-numeros" data-numeros-da-base="">
        {itens.map(([valor, rotulo]) => (
          <div key={rotulo} className="cartao">
            <dt>{milhares(valor)}</dt>
            <dd>{rotulo}</dd>
          </div>
        ))}
      </dl>
      <p className="dados-frase">{`Medido em ${medido_em_curto}.`}</p>
    </>
  );
}

export function Dados() {
  const { totais, fontes, modulos } = catalogo;
  const emConsulta = fontes.filter((f) => f.situacao === "em consulta");
  return (
    <PaginaDeLeitura
      olho="Dados"
      titulo="A base por trás de cada número"
      subtitulo="Cada tabela diz de onde vem, o que ficou público e quando, e o que pode ser repassado."
      sumario={SECOES.map((texto) => ({ id: ancora(texto), texto }))}
    >
      <h2 id={ancora(SECOES[0])}>{SECOES[0]}</h2>
      <p className="dados-resumo">
        {`${totais.tabelas} tabelas, de ${totais.fontes} fontes públicas, em ${totais.modulos} módulos.`}
      </p>
      <NumerosDaBase />
      <p>
        Toda tabela tem um contrato: quem cuida dela, a versão, as chaves, as datas, a licença e a
        frequência de atualização. A lista abaixo é gerada desse contrato; tabela ou fonte nova
        aparece aqui sozinha.
      </p>

      <h2 id={ancora(SECOES[1])}>{SECOES[1]}</h2>
      <div className="grade dados-regras">
        {REGRAS_DA_BASE.map(([titulo, texto]) => (
          <article key={titulo} className="cartao">
            <h3>{titulo}</h3>
            <p>{texto}</p>
          </article>
        ))}
      </div>

      <h2 id={ancora(SECOES[2])}>{SECOES[2]}</h2>
      <p>
        {`As ${totais.tabelas} tabelas em ${totais.modulos} módulos. "Desde" é o começo do histórico guardado; "atualização" é a frequência com que a fonte publica.`}
      </p>
      <p {...COM_CONSULTA}>{FRASE_DA_CONSULTA}</p>
      <p>
        <input
          type="search"
          className="dados-busca"
          data-filtro-tabelas=""
          placeholder="Buscar por nome da tabela ou fonte"
          aria-label="Buscar tabela por nome ou fonte"
          hidden
        />
      </p>
      <p className="dados-vazio" data-filtro-vazio="" hidden>
        Nenhuma tabela com esse nome.
      </p>
      {modulos.map((m) => (
        <TabelasDoModulo key={m.chave} chave={m.chave} nome={m.nome} />
      ))}
      <div {...COM_CONSULTA}>
        <div data-consulta-base="">
          <ConsultaDaBase />
        </div>
      </div>

      <h2 id={ancora(SECOES[3])}>{SECOES[3]}</h2>
      <p>
        {`${totais.fontes} fontes, cada uma com a licença que ela mesma publica. O que não tem resposta escrita da fonte sobre uso comercial leva o selo "${SEM_RESPOSTA}".`}
      </p>
      <div className="grade dados-fontes">
        {fontes.map((f) => (
          <CartaoDaFonte key={f.licenca} f={f} />
        ))}
      </div>

      <h2 id={ancora(SECOES[4])}>{SECOES[4]}</h2>
      <p>
        Temos <strong>{`${totais.familias} fontes públicas`}</strong>
        {`: ${totais.familias_em_uso} já chegam a uma tela, a um relatório, à ficha ou à API, e ${totais.familias - totais.familias_em_uso} estão guardadas no nosso acervo, com o arquivo original e a data da coleta, esperando o dia em que viram tabela. Para cada uma mostramos o órgão que a publica, a licença que ela mesma escreve, se o dado pode ser repassado e o dia em que lemos os termos dela pela última vez.`}
      </p>
      <p>
        <strong>Em uso</strong> quer dizer que algum número do TickerLab sai dela.{" "}
        <strong>Guardada</strong> quer dizer que coletamos e guardamos, mas ainda não mostramos nada
        dela. <strong>A confirmar</strong> quer dizer que a fonte não respondeu por escrito sobre
        uso comercial; até a resposta, tratamos como não comercial. <strong>Não comercial</strong>{" "}
        e <strong>só uso interno</strong> são fontes que usamos para conferir ou pesquisar, sem
        repassar o dado.
      </p>
      <p>
        Os preços das ações vêm do Yahoo Finance, cujos termos são de uso pessoal: mostramos com a
        fonte citada enquanto a base própria de preços, feita com os arquivos da B3, não fica
        pronta.
      </p>
      <div
        className="dados-filtro-uso"
        role="group"
        aria-label="Mostrar fontes"
        data-filtro-uso=""
        hidden
      >
        {FILTROS_DE_USO.map(([uso, rotulo], i) => (
          <button key={uso} type="button" data-uso={uso} aria-pressed={i === 0 ? "true" : "false"}>
            {rotulo}
          </button>
        ))}
      </div>
      <div className="tabela dados-familias">
        <table>
          <thead>
            <tr>
              <th>Órgão</th>
              <th>Uso</th>
              <th>Pode repassar?</th>
              <th>Licença</th>
              <th>Termos lidos em</th>
            </tr>
          </thead>
          <tbody>
            {naOrdemDaPagina(catalogo.familias_de_fontes).map((f) => (
              <LinhaDaFamilia key={f.familia} f={f} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="dados-frase">
        Isto não é parecer jurídico. A lista sai do código do TickerLab e muda sozinha quando entra
        fonte nova.
      </p>

      <h2 id={ancora(SECOES[5])}>{SECOES[5]}</h2>
      <ul>
        <li>
          <strong>Cotações com licença comercial da bolsa.</strong> Os preços do app vêm de dados
          públicos de mercado, que podem ter atraso ou erros. A licença de dados de negociação da
          bolsa é paga e ainda não foi contratada.
        </li>
        <li>
          <strong>
            {emConsulta.length === 1
              ? "Uma fonte em consulta."
              : `${emConsulta.length} fontes em consulta.`}
          </strong>{" "}
          {emConsulta.map((f) => f.orgao).join(", ")}: os dados estão na base, mas sem resposta
          escrita da fonte sobre uso comercial. Até a resposta, tratamos como não comercial.
        </li>
        <li>
          <strong>Bases pagas de terceiros.</strong> Nada delas entra na nossa base. Quando servem
          de comparação, é só como gabarito de conferência.
        </li>
      </ul>

      <h2 id={ancora(SECOES[6])}>{SECOES[6]}</h2>
      <p>
        Pegue uma conta de uma empresa, a CPFL, por exemplo. O caminho para conferir o número é
        sempre o mesmo:
      </p>
      <ol>
        <li>
          Veja de qual tabela ele vem e qual é a fonte: o nome da tabela e o órgão estão na lista
          acima.
        </li>
        <li>
          Pergunte "como era na data": a tabela <code>demonstracoes_como_era</code> guarda cada
          valor que a conta já teve e o dia em que ficou público.
        </li>
        <li>Abra a licença da fonte e veja o que pode ser repassado.</li>
      </ol>
      <ComoFoiCalculado resumo="Por que guardar cada versão do número">
        <p>
          As empresas reapresentam balanços e o balanço seguinte refaz o ano anterior. Quem guarda
          só o valor mais novo não consegue saber o que se sabia numa data passada. Guardamos uma
          linha por valor diferente, com o dia em que ficou público, e por isso uma análise de uma
          data passada usa só o que existia naquele dia, sem olhar o futuro.
        </p>
      </ComoFoiCalculado>
      <p className="dados-aviso">
        Os dados vêm de fontes públicas e podem ter atraso ou erros. Nada aqui é recomendação de
        investimento.
      </p>
    </PaginaDeLeitura>
  );
}
