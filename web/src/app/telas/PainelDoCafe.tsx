// Painel do café no app novo (plano do café, PR 11; ADR 0062, Emenda 2: só no React). Uma caixa por
// assunto: preço de referência e spread, câmbio, fundos, exportações, balanço mundial, safra e
// termômetro da CONAB, bienalidade, clima da região, calendário e contrapartes. Cada caixa diz o que
// é, a fonte e a data do número mais novo; sem dado, o motivo. Tudo "como estava" no dia da resposta.
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { Carregando } from "../Carregando";
import { SEM_NUMERO, formatarData, formatarDecimal, formatarMes, formatarPct } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type {
  BalancoDoCafeV1,
  BienalidadeDoCafeV1,
  BlocoDoCafeV1,
  CalendarioDoCafeV1,
  CambioDoCafeV1,
  ClimaDaRegiaoV1,
  ContrapartesDoCafeV1,
  ExportacoesDoCafeV1,
  FundosDoCafeV1,
  PainelDoCafeV1,
  PontoAnualDoCafeV1,
  PrecoDoCafeV1,
  SafraDoCafeV1,
  TermometroDaConabV1,
} from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const TIPOS = [
  { id: "arabica", nome: "Arábica" },
  { id: "conilon", nome: "Conilon (robusta)" },
];
const TIPO_PADRAO = "arabica";
const MINIMO_NO_GRAFICO = 2;
// o nome curto de cada fase (os temas de src/commodities/cafe/calendario.py)
const NOME_DA_FASE: Record<string, string> = {
  florada: "Florada",
  enchimento: "Enchimento do grão",
  maturacao: "Maturação",
  repouso: "Repouso dos ramos",
  colheita: "Colheita",
  geada: "Janela de geada",
  vegetacao: "Vegetação da safra seguinte",
  inducao: "Indução das gemas da safra seguinte",
};

/** Número inteiro com ponto de milhar: 11339809.25 → "11.339.809". */
function inteiro(valor: number | null): string {
  if (valor === null || !Number.isFinite(valor)) return SEM_NUMERO;
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

/** Variação que já vem em %: 1.4168 → "+1,42%". */
function variacao(valor: number | null): string {
  if (valor === null) return SEM_NUMERO;
  return `${valor > 0 ? "+" : ""}${formatarDecimal(valor)}%`;
}

const formatarAno = (iso: string) => iso.slice(0, 4);
const nomeDaFase = (tema: string) => NOME_DA_FASE[tema] ?? tema;

function Numero({ rotulo, valor, legenda }: { rotulo: string; valor: string; legenda?: string }) {
  return (
    <div className="numero-do-painel">
      <span className="numero-rotulo">{rotulo}</span>
      <span className="numero-valor">{valor}</span>
      {legenda ? <span className="legenda-do-numero">{legenda}</span> : null}
    </div>
  );
}

/** A caixa: título, o que é, o conteúdo (ou "Sem dado" com o motivo), a fonte e a data. */
function Caixa<T>({ bloco, children }: { bloco: BlocoDoCafeV1<T>; children: (conteudo: T) => ReactNode }) {
  return (
    <section aria-label={bloco.titulo} className="bloco-do-cafe">
      <h2>{bloco.titulo}</h2>
      <p className="apagado">{bloco.o_que_e}</p>
      {bloco.conteudo === null ? (
        <p className="sem-dado-do-cafe">
          <strong>Sem dado.</strong> {bloco.motivo_sem_dado}
        </p>
      ) : (
        children(bloco.conteudo)
      )}
      <p className="apagado fonte-do-bloco">
        {bloco.fonte}
        {bloco.data ? ` Dado mais novo: ${formatarData(bloco.data)}.` : ""}
      </p>
    </section>
  );
}

function Preco({ dados }: { dados: PrecoDoCafeV1 }) {
  const { item, spread, marcos } = dados;
  return (
    <>
      <div className="numeros">
        <Numero
          rotulo={`${item.nome} (${item.unidade})`}
          valor={formatarDecimal(item.ultimo_valor)}
          legenda={`Média de ${formatarMes(item.ultimo_mes)}; ${variacao(item.variacao_12_meses)} em 12 meses.`}
        />
      </div>
      {item.historico.length >= MINIMO_NO_GRAFICO ? (
        <GraficoDeLinha
          titulo={`${item.nome} (${item.unidade}), média mensal`}
          datas={item.historico.map((p) => p.mes)}
          series={[
            { nome: "Banco Mundial (Pink Sheet)", cor: "var(--serie-1)", valores: item.historico.map((p) => p.bm) },
            ...(item.com_fmi
              ? [{ nome: "FMI (PCPS)", cor: "var(--serie-2)", valores: item.historico.map((p) => p.fmi) }]
              : []),
          ]}
          formatarValor={formatarDecimal}
          formatarDia={formatarMes}
        />
      ) : null}
      {item.nota_das_fontes ? <p className="apagado">{item.nota_das_fontes}</p> : null}
      {spread.length >= MINIMO_NO_GRAFICO ? (
        <GraficoDeLinha
          titulo="Spread arábica menos robusta (centavos de US$ por libra-peso)"
          datas={spread.map((p) => p.mes)}
          series={[{ nome: "Arábica menos robusta", cor: "var(--serie-1)", valores: spread.map((p) => p.spread) }]}
          formatarValor={formatarDecimal}
          formatarDia={formatarMes}
        />
      ) : null}
      {marcos.length > 0 ? (
        <div className="tabela-rolavel">
          <table className="tabela-do-app">
            <caption>Episódios que mexeram com o preço</caption>
            <thead>
              <tr>
                <th scope="col">Quando</th>
                <th scope="col">O que houve</th>
                <th scope="col">Fonte</th>
              </tr>
            </thead>
            <tbody>
              {marcos.map((m) => (
                <tr key={m.data}>
                  <td>{formatarMes(m.data)}</td>
                  <td>{m.texto}</td>
                  <td>{m.fonte}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

function Cambio({ dados }: { dados: CambioDoCafeV1 }) {
  return (
    <>
      <div className="numeros">
        <Numero
          rotulo="Dólar (R$ por US$)"
          valor={formatarDecimal(dados.ultimo_valor)}
          legenda={`PTAX de ${formatarData(dados.ultimo_dia)}; ${variacao(dados.variacao_12_meses)} em 12 meses.`}
        />
      </div>
      <GraficoDeLinha
        titulo="Dólar (R$ por US$), média mensal"
        datas={dados.historico.map((p) => p.mes)}
        series={[{ nome: "PTAX (venda)", cor: "var(--serie-1)", valores: dados.historico.map((p) => p.valor) }]}
        formatarValor={formatarDecimal}
        formatarDia={formatarMes}
      />
    </>
  );
}

function Fundos({ dados }: { dados: FundosDoCafeV1 }) {
  return (
    <>
      <div className="numeros">
        <Numero rotulo="Posição líquida (lotes)" valor={inteiro(dados.liquido_lotes)} />
        <Numero rotulo="Em sacas de 60 kg" valor={inteiro(dados.liquido_sacas)} />
        <Numero
          rotulo="Fatia do interesse aberto"
          valor={formatarPct(dados.fracao_do_interesse_aberto)}
          legenda={`De ${inteiro(dados.interesse_aberto_lotes)} lotes em aberto.`}
        />
        <Numero
          rotulo="Comprados / vendidos (lotes)"
          valor={`${inteiro(dados.comprados_lotes)} / ${inteiro(dados.vendidos_lotes)}`}
          legenda={`Relatório de ${formatarData(dados.relatorio)}.`}
        />
      </div>
      <GraficoDeLinha
        titulo="Posição líquida dos fundos (lotes), semana a semana"
        datas={dados.historico.map((p) => p.relatorio)}
        series={[{ nome: "Comprados menos vendidos", cor: "var(--serie-1)", valores: dados.historico.map((p) => p.liquido_lotes) }]}
        formatarValor={inteiro}
      />
      <p className="aviso-do-app" role="note">
        {dados.legenda}
      </p>
    </>
  );
}

function Exportacoes({ dados }: { dados: ExportacoesDoCafeV1 }) {
  const periodo = `De ${formatarMes(dados.primeiro_mes)} a ${formatarMes(dados.ultimo_mes)}.`;
  return (
    <>
      <div className="numeros">
        <Numero rotulo="Sacas de 60 kg em 12 meses" valor={inteiro(dados.sacas)} legenda={periodo} />
        <Numero rotulo="Valor FOB (US$)" valor={inteiro(dados.fob_usd)} legenda={periodo} />
        <Numero
          rotulo="Fatia do Espírito Santo"
          valor={formatarPct(dados.fracao_do_espirito_santo)}
          legenda="Pista do conilon, não a conta dele."
        />
      </div>
      {dados.destinos.length > 0 ? (
        <div className="tabela-rolavel">
          <table className="tabela-do-app">
            <caption>Para onde foi o café</caption>
            <thead>
              <tr>
                <th scope="col">País</th>
                <th scope="col">Sacas</th>
                <th scope="col">US$ FOB</th>
                <th scope="col">Fatia</th>
              </tr>
            </thead>
            <tbody>
              {dados.destinos.map((d) => (
                <tr key={d.pais}>
                  <td>{d.pais}</td>
                  <td className="numero">{inteiro(d.sacas)}</td>
                  <td className="numero">{inteiro(d.fob_usd)}</td>
                  <td className="numero">{formatarPct(d.fracao)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="apagado">{dados.nota}</p>
    </>
  );
}

/** Um ponto por ano-safra, numa série por rótulo ("mundo", "BR", "arabica"...). */
function seriesAnuais(pontos: PontoAnualDoCafeV1[], nomes: Record<string, string>) {
  const anos = [...new Set(pontos.map((p) => p.ano_safra))].sort((a, b) => a - b);
  const rotulos = [...new Set(pontos.map((p) => p.rotulo))];
  return {
    datas: anos.map((a) => `${a}-01-01`),
    series: rotulos.map((rotulo, i) => ({
      nome: nomes[rotulo] ?? rotulo,
      cor: `var(--serie-${i + 1})`,
      valores: anos.map((a) => pontos.find((p) => p.ano_safra === a && p.rotulo === rotulo)?.valor ?? null),
    })),
  };
}

function Balanco({ dados }: { dados: BalancoDoCafeV1 }) {
  const estoque = seriesAnuais([...dados.estoque_consumo_mundo, ...dados.estoque_consumo_brasil], {
    mundo: "Mundo",
    BR: "Brasil",
  });
  const fatia = seriesAnuais(dados.participacao_do_brasil, { arabica: "Arábica", robusta: "Robusta (conilon)" });
  return (
    <>
      <GraficoDeLinha
        titulo="Estoque final sobre o consumo, por ano-safra"
        {...estoque}
        formatarValor={(v) => formatarPct(v)}
        formatarDia={formatarAno}
      />
      <GraficoDeLinha
        titulo="Fatia do Brasil na produção mundial, por ano-safra"
        {...fatia}
        formatarValor={(v) => formatarPct(v)}
        formatarDia={formatarAno}
      />
      <p className="apagado">Último ano-safra com números: {dados.ultima_safra}.</p>
    </>
  );
}

function Safra({ dados }: { dados: SafraDoCafeV1 }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <caption>
          Safra {dados.safra}, {dados.levantamento}º levantamento (divulgado em {formatarData(dados.divulgado_em)})
        </caption>
        <thead>
          <tr>
            <th scope="col">UF</th>
            <th scope="col">Área em produção (ha)</th>
            <th scope="col">Produtividade (sc/ha)</th>
            <th scope="col">Produção (mil sacas)</th>
          </tr>
        </thead>
        <tbody>
          {dados.linhas.map((l) => (
            <tr key={l.uf}>
              <td>{l.uf === "BRASIL" ? "Brasil" : l.uf}</td>
              <td className="numero">{inteiro(l.area_producao_ha)}</td>
              <td className="numero">{formatarDecimal(l.produtividade_sc_ha)}</td>
              <td className="numero">{inteiro(l.producao_mil_sacas)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Termometro({ dados }: { dados: TermometroDaConabV1 }) {
  return (
    <>
      <div className="numeros">
        <Numero rotulo="Erro médio do 1º levantamento" valor={variacao(dados.vies_medio_pct)} />
        <Numero rotulo="Menor erro" valor={variacao(dados.menor_erro_pct)} />
        <Numero rotulo="Maior erro" valor={variacao(dados.maior_erro_pct)} />
      </div>
      <div className="tabela-rolavel">
        <table className="tabela-do-app">
          <caption>1º levantamento contra o número final, safra a safra</caption>
          <thead>
            <tr>
              <th scope="col">Safra</th>
              <th scope="col">Erro (%)</th>
              <th scope="col">Erro (mil sacas)</th>
            </tr>
          </thead>
          <tbody>
            {dados.erros.map((e) => (
              <tr key={e.safra}>
                <td>{e.safra}</td>
                <td className="numero">{variacao(e.erro_pct)}</td>
                <td className="numero">{inteiro(e.erro_mil_sacas)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="apagado">{dados.nota}</p>
    </>
  );
}

function Bienalidade({ dados }: { dados: BienalidadeDoCafeV1 }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <caption>Ano cheio ou vazio, pela produção do Brasil</caption>
        <thead>
          <tr>
            <th scope="col">Safra</th>
            <th scope="col">Ano</th>
            <th scope="col">Produção (mil sacas)</th>
          </tr>
        </thead>
        <tbody>
          {dados.marcas.map((m) => (
            <tr key={`${m.safra}-${m.uf}`}>
              <td>{m.safra}</td>
              <td>{m.rotulo ?? SEM_NUMERO}</td>
              <td className="numero">{inteiro(m.valor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Clima({ dados }: { dados: ClimaDaRegiaoV1 }) {
  const { chuva, temperatura } = dados;
  const periodo = `De ${formatarMes(chuva.inicio)} a ${formatarMes(chuva.fim)}, ${chuva.n_estacoes} pontos de medida.`;
  return (
    <div className="numeros">
      <Numero rotulo={`Chuva em 3 meses, ${dados.nome_da_regiao} (mm)`} valor={inteiro(chuva.valor)} legenda={periodo} />
      <Numero
        rotulo="Contra a normal"
        valor={formatarPct(chuva.razao_da_normal)}
        legenda={`Normal: ${inteiro(chuva.normal)} mm.`}
      />
      <Numero
        rotulo={`Mínima média de ${formatarMes(temperatura.competencia)} (°C)`}
        valor={formatarDecimal(temperatura.tmin_media_c)}
        legenda={`Normal: ${formatarDecimal(temperatura.tmin_normal_c)} °C.`}
      />
      <Numero rotulo="Dias com mínima abaixo de 2 °C" valor={inteiro(temperatura.dias_tmin_abaixo_de_2c)} />
    </div>
  );
}

function Calendario({ dados }: { dados: CalendarioDoCafeV1 }) {
  const { fase } = dados;
  return (
    <>
      <ul className="lista-do-cafe">
        <li>Safra em curso: {nomeDaFase(fase.safra_em_curso)}.</li>
        <li>Safra seguinte: {nomeDaFase(fase.safra_seguinte)}.</li>
        <li>{fase.em_colheita ? "É mês de colheita na região." : "Não é mês de colheita na região."}</li>
        {fase.na_janela_de_geada ? <li>É a janela de geada (junho a agosto).</li> : null}
      </ul>
      {dados.itens.map((item) => (
        <div key={item.tema}>
          <h3>{nomeDaFase(item.tema)}</h3>
          <p>{item.texto}</p>
        </div>
      ))}
    </>
  );
}

function Contrapartes({ dados }: { dados: ContrapartesDoCafeV1 }) {
  return (
    <>
      {dados.fichas.map((ficha) => (
        <article key={ficha.id} aria-label={ficha.nome} className="ficha-do-cafe">
          <h3>{ficha.nome}</h3>
          <p className="apagado">
            {[ficha.tipo, ficha.uf, ficha.cnpj ? `CNPJ ${ficha.cnpj}` : null].filter(Boolean).join(" · ")}
          </p>
          <ul className="lista-do-cafe">
            {ficha.fatos.map((f) => (
              <li key={`${f.fato}-${f.data}`}>
                {f.descricao} ({formatarData(f.data)};{" "}
                <a href={f.fonte} target="_blank" rel="noreferrer">
                  {f.veiculo}
                </a>
                , {formatarData(f.divulgado_em)})
              </li>
            ))}
          </ul>
          <h4>O que não sabemos</h4>
          <ul className="lista-do-cafe">
            {ficha.o_que_nao_sabemos.map((texto) => (
              <li key={texto}>{texto}</li>
            ))}
          </ul>
        </article>
      ))}
    </>
  );
}

function Seletores({ dados, tipo }: { dados: PainelDoCafeV1 | null; tipo: string }) {
  const [busca, setBusca] = useSearchParams();
  const escolherTipo = (id: string) => setBusca({ tipo: id }); // outro tipo: volta à região padrão
  const escolherRegiao = (regiao: string) => setBusca({ tipo, regiao });
  return (
    <div className="formulario-do-app seletores-do-cafe">
      <div role="group" aria-label="Tipo de café" className="tipos-do-cafe">
        {TIPOS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={t.id === tipo ? "botao primario" : "botao"}
            aria-pressed={t.id === tipo}
            onClick={() => escolherTipo(t.id)}
          >
            {t.nome}
          </button>
        ))}
      </div>
      {dados ? (
        <label>
          Região do clima e do calendário
          <select value={busca.get("regiao") ?? dados.regiao} onChange={(e) => escolherRegiao(e.target.value)}>
            {dados.regioes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nome}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </div>
  );
}

function Resultado({ dados }: { dados: PainelDoCafeV1 }) {
  return (
    <>
      <p className="apagado">
        {dados.nome_do_tipo}, como estava em {formatarData(dados.dia)}.
      </p>
      <div className="blocos-do-cafe">
        <Caixa bloco={dados.preco_de_referencia}>{(c) => <Preco dados={c} />}</Caixa>
        <Caixa bloco={dados.cambio}>{(c) => <Cambio dados={c} />}</Caixa>
        <Caixa bloco={dados.fundos}>{(c) => <Fundos dados={c} />}</Caixa>
        <Caixa bloco={dados.exportacoes}>{(c) => <Exportacoes dados={c} />}</Caixa>
        <Caixa bloco={dados.balanco}>{(c) => <Balanco dados={c} />}</Caixa>
        <Caixa bloco={dados.safra}>{(c) => <Safra dados={c} />}</Caixa>
        <Caixa bloco={dados.termometro}>{(c) => <Termometro dados={c} />}</Caixa>
        <Caixa bloco={dados.bienalidade}>{(c) => <Bienalidade dados={c} />}</Caixa>
        <Caixa bloco={dados.clima}>{(c) => <Clima dados={c} />}</Caixa>
        <Caixa bloco={dados.calendario}>{(c) => <Calendario dados={c} />}</Caixa>
        <Caixa bloco={dados.contrapartes}>{(c) => <Contrapartes dados={c} />}</Caixa>
      </div>
    </>
  );
}

export function PainelDoCafe({ pagina }: { pagina: PaginaDoApp }) {
  const [busca] = useSearchParams();
  const tipo = TIPOS.some((t) => t.id === busca.get("tipo")) ? (busca.get("tipo") as string) : TIPO_PADRAO;
  const regiao = busca.get("regiao") ?? undefined;
  const pedido = usarPedido<PainelDoCafeV1>(pagina.contrato?.rota ?? "", { tipo, regiao });
  const dados = pedido.estado === "pronto" ? pedido.dados : null;
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      <p className="aviso-do-app" role="note">
        <strong>Preço de referência mensal; o diário depende de licença.</strong>
      </p>
      <Seletores dados={dados} tipo={tipo} />
      {pedido.estado === "carregando" ? (
        <Carregando tipo="painel" rotulo="Montando o painel do café…" />
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Resultado dados={pedido.dados} />
      )}
    </section>
  );
}
