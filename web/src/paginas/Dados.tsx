// Dados: a base que alimenta o TickerLab, gerada do catálogo de contratos (base/contratos/catalogo.json).
// Nenhum número é digitado aqui: tabelas, fontes e módulos vêm de `catalogo` (ADRs 0048, 0065 e 0099).
// A comparação com qualquer outra base é só pelo rigor: linhagem, "como era na data", licença por
// tabela e explicação recolhida. Nada aqui é recomendação de investimento.
import { type FonteDaBase, type TabelaDaBase, catalogo } from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { PaginaDeLeitura, ancora } from "../site/Leitura";

export const DADOS = {
  caminho: "/dados.html",
  titulo: "Dados",
  descricao:
    "A base do TickerLab: cada tabela com a fonte, a licença e a data em que o dado ficou público, " +
    "para quem analisa empresas no Brasil.",
  atual: "/dados.html",
};

const SECOES = [
  "A base em uma linha",
  "Quatro regras que valem para toda tabela",
  "O que há na base",
  "De onde vêm os dados",
  "O que ainda não está na base",
  "Como auditar um número",
];

const REGRAS: [string, string][] = [
  [
    "Como era na data",
    "Guardamos o que estava público em cada dia, não só o valor de hoje. Uma consulta a uma data " +
      "nunca enxerga o que só ficou público depois dela.",
  ],
  [
    "Linhagem",
    "Cada tabela diz de qual fonte vem, qual versão do contrato a descreve e desde quando há histórico.",
  ],
  [
    "Licença por tabela",
    "Cada tabela leva a licença da sua fonte e diz o que pode ser repassado. Onde ainda não há " +
      "resposta escrita da fonte, a página avisa.",
  ],
  [
    "Explicação",
    "O que cada dado é e como foi calculado vem escrito em português e recolhido: quem quer " +
      "conferir abre, quem só quer o resultado não é atrapalhado.",
  ],
];

const SEM_RESPOSTA = "licença em consulta";

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
      <p>
        Toda tabela tem um contrato: quem cuida dela, a versão, as chaves, as datas, a licença e a
        frequência de atualização. A lista abaixo é gerada desse contrato; tabela ou fonte nova
        aparece aqui sozinha.
      </p>

      <h2 id={ancora(SECOES[1])}>{SECOES[1]}</h2>
      <div className="grade dados-regras">
        {REGRAS.map(([titulo, texto]) => (
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

      <h2 id={ancora(SECOES[5])}>{SECOES[5]}</h2>
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
