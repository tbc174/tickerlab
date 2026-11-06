// Mapa do café no app novo (plano do café, PR 10): produção e área de cada município (PAM do IBGE) e
// a chuva e a geada da região contra a normal, arábica ou conilon. Os textos (o que é isto, fonte,
// motivo de cada cinza) chegam prontos da API; a tela só pinta. O desenho do mapa é o
// MapaDeMunicipios (SVG, sem biblioteca de mapa).
import { useMemo, useState } from "react";
import type { PaginaDoApp } from "../../conteudo";
import { formatarData, formatarDecimal } from "../formatar";
import { MapaDeMunicipios } from "../graficos/MapaDeMunicipios";
import type { CamadaDoMapaV1, MapaDoCafeV1, MunicipioDoMapaV1, RegiaoDoMapaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const TIPOS = [
  { valor: "arabica", nome: "Arábica" },
  { valor: "conilon", nome: "Conilon (robusta)" },
];
const FAIXAS = 5; // a cor de cada município vem de uma de 5 faixas (quintis dos que têm número)

/** O "o que é isto" de cada caixa, no mesmo botão "?" do resto do app. */
function OQueE({ texto, rotulo }: { texto: string; rotulo: string }) {
  return (
    <details className="ajuda">
      <summary aria-label={`O que é ${rotulo}`}>?</summary>
      <div className="ajuda-texto">
        <p>{texto}</p>
      </div>
    </details>
  );
}

// --- cores ----------------------------------------------------------------------------------------
function limitesDasFaixas(valores: number[]): number[] {
  const ordenados = [...valores].sort((a, b) => a - b);
  return Array.from({ length: FAIXAS - 1 }, (_, i) => ordenados[Math.floor(((i + 1) * ordenados.length) / FAIXAS)]);
}

function faixa(valor: number, limites: number[]): number {
  const i = limites.findIndex((l) => valor < l);
  return i === -1 ? limites.length : i;
}

/** A cor de uma faixa: mais azul é mais; na chuva, abaixo da normal puxa para o âmbar. */
function cor(camada: CamadaDoMapaV1, valor: number | null, limites: number[]): string {
  if (valor === null) return "var(--linha-forte)";
  if (camada.escala === "divergente" && camada.referencia !== null) {
    const distancia = Math.min(Math.abs(valor - camada.referencia) / camada.referencia, 1);
    const tom = valor < camada.referencia ? "var(--atencao)" : "var(--azul)";
    return `color-mix(in srgb, ${tom} ${Math.round(15 + distancia * 85)}%, var(--fundo))`;
  }
  return `color-mix(in srgb, var(--azul) ${Math.round(20 + (faixa(valor, limites) * 80) / (FAIXAS - 1))}%, var(--fundo))`;
}

function formatarValor(valor: number | null, camada: CamadaDoMapaV1): string {
  if (valor === null) return "sem dado";
  const numero = camada.unidade === "% da normal" ? formatarDecimal(valor) : valor.toLocaleString("pt-BR");
  return camada.unidade === "% da normal" ? `${numero}% da normal` : `${numero} ${camada.unidade}`;
}

// --- partes da tela -------------------------------------------------------------------------------
function Legenda({ camada, limites }: { camada: CamadaDoMapaV1; limites: number[] }) {
  const itens =
    camada.escala === "divergente"
      ? [
          { cor: cor(camada, 0, limites), texto: "bem abaixo da normal" },
          { cor: cor(camada, camada.referencia ?? 100, limites), texto: "na normal" },
          { cor: cor(camada, (camada.referencia ?? 100) * 2, limites), texto: "bem acima" },
        ]
      : limites.length === 0
        ? []
        : [
            { cor: cor(camada, limites[0] - 1, limites), texto: `menos de ${formatarValor(limites[0], camada)}` },
            {
              cor: cor(camada, limites[limites.length - 1], limites),
              texto: `${formatarValor(limites[limites.length - 1], camada)} ou mais`,
            },
          ];
  return (
    <ul className="legenda-do-mapa" aria-label="Legenda do mapa">
      {itens.map((i) => (
        <li key={i.texto}>
          <span className="amostra" style={{ background: i.cor }} />
          {i.texto}
        </li>
      ))}
      <li>
        <span className="amostra" style={{ background: cor(camada, null, limites) }} />
        sem dado (o motivo aparece ao escolher o município)
      </li>
    </ul>
  );
}

function Ficha({
  municipio,
  regiao,
  dados,
}: {
  municipio: MunicipioDoMapaV1;
  regiao: RegiaoDoMapaV1 | undefined;
  dados: MapaDoCafeV1;
}) {
  const nomeDoTipo = TIPOS.find((t) => t.valor === dados.tipo)?.nome ?? dados.tipo;
  return (
    <section className="ficha-do-municipio" aria-label={`Ficha de ${municipio.nome}`}>
      <h2>
        {municipio.nome} ({municipio.uf})
      </h2>
      <p className="apagado">
        {regiao ? `Região produtora: ${regiao.nome}.` : "Fora das regiões produtoras do cadastro."} Café: {nomeDoTipo}.
      </p>
      <dl className="numeros-da-ficha">
        {dados.camadas.map((c) => (
          <div key={c.chave}>
            <dt>
              {c.titulo} <OQueE texto={c.o_que_e} rotulo={c.titulo} />
            </dt>
            <dd>{formatarValor(municipio.valores[c.chave] ?? null, c)}</dd>
            <dd className="legenda-do-numero">{municipio.sem_dado[c.chave] ?? c.fonte}</dd>
          </div>
        ))}
        <div>
          <dt>
            Área com café vista por satélite{" "}
            <OQueE
              texto="Os hectares que o MapBiomas classifica como café nas imagens de satélite do ano, todos os tipos juntos. Serve para conferir a área do IBGE: não separa arábica de conilon."
              rotulo="a área do MapBiomas"
            />
          </dt>
          <dd>{municipio.area_mapbiomas_ha === null ? "sem dado" : `${formatarDecimal(municipio.area_mapbiomas_ha)} ha`}</dd>
          <dd className="legenda-do-numero">MapBiomas, Coleção 11, ano {dados.ano}</dd>
        </div>
      </dl>
      {regiao ? (
        <>
          <h3>O clima da região</h3>
          <p>{regiao.chuva.texto}</p>
          <p>{regiao.geada.texto}</p>
          <h3>
            A fase do café em {regiao.nome}{" "}
            <OQueE
              texto="O cafeeiro leva dois anos para fazer uma safra: enquanto uma amadurece, a planta já forma os ramos da seguinte. A fase é a do calendário do mês, não uma leitura da lavoura."
              rotulo="a fase do café"
            />
          </h3>
          <p>{regiao.fase}</p>
          {regiao.o_que_o_mercado_olha.map((item) => (
            <details key={item.titulo} className="item-do-mes">
              <summary>{item.titulo}</summary>
              <p>{item.texto}</p>
            </details>
          ))}
        </>
      ) : null}
    </section>
  );
}

function Resultado({ dados }: { dados: MapaDoCafeV1 }) {
  const [chaveDaCamada, setChaveDaCamada] = useState(dados.camadas[0]?.chave ?? "");
  const [escolhido, setEscolhido] = useState("");
  const camada = dados.camadas.find((c) => c.chave === chaveDaCamada) ?? dados.camadas[0];
  const porCodigo = useMemo(() => new Map(dados.municipios.map((m) => [m.codigo, m])), [dados.municipios]);
  const regioes = useMemo(() => new Map(dados.regioes.map((r) => [r.id, r])), [dados.regioes]);
  const limites = useMemo(
    () =>
      limitesDasFaixas(
        dados.municipios.map((m) => m.valores[camada.chave]).filter((v): v is number => v !== null && v !== undefined),
      ),
    [dados.municipios, camada.chave],
  );
  const valorDe = (codigo: string) => porCodigo.get(codigo)?.valores[camada.chave] ?? null;
  const municipio = porCodigo.get(escolhido);
  const ordenados = [...dados.municipios].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  return (
    <>
      {/* a caixa e os campos do formulário do app, sem <form>: cada escolha já muda o mapa */}
      <div className="formulario-do-app">
        <div className="campos-do-formulario">
          <label>
            <span>Camada</span>
            <select value={camada.chave} onChange={(ev) => setChaveDaCamada(ev.target.value)}>
              {dados.camadas.map((c) => (
                <option key={c.chave} value={c.chave}>
                  {c.titulo}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Município</span>
            <select value={escolhido} onChange={(ev) => setEscolhido(ev.target.value)}>
              <option value="">Escolha um município</option>
              {ordenados.map((m) => (
                <option key={m.codigo} value={m.codigo}>
                  {m.nome} ({m.uf})
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <section className="caixa-do-mapa" aria-label={camada.titulo}>
        <h2>
          {camada.titulo} <OQueE texto={camada.o_que_e} rotulo={camada.titulo} />
        </h2>
        <p className="legenda-do-numero">{camada.fonte}</p>
        {dados.malha.features.length === 0 ? (
          <p className="apagado">O contorno dos municípios não veio com este mapa; a lista acima tem todos.</p>
        ) : (
          <MapaDeMunicipios
            malha={dados.malha}
            rotulo={`Mapa: ${camada.titulo}`}
            corDe={(codigo) => cor(camada, valorDe(codigo), limites)}
            semDado={(codigo) => valorDe(codigo) === null}
            textoDe={(codigo) => {
              const m = porCodigo.get(codigo);
              const valor = valorDe(codigo);
              const nome = m ? `${m.nome} (${m.uf})` : codigo;
              return `${nome}: ${valor === null ? (m?.sem_dado[camada.chave] ?? "sem dado") : formatarValor(valor, camada)}`;
            }}
            escolhido={escolhido}
            aoEscolher={setEscolhido}
          />
        )}
        <Legenda camada={camada} limites={limites} />
      </section>
      {municipio ? (
        <Ficha municipio={municipio} regiao={municipio.regiao ? regioes.get(municipio.regiao) : undefined} dados={dados} />
      ) : (
        <p className="apagado">Escolha um município no mapa ou na lista para ver a ficha.</p>
      )}
      <section aria-label="Fontes">
        <h3>Fontes</h3>
        <ul className="apagado">
          {dados.fontes.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
        <p className="apagado">
          Dados como estavam em {formatarData(dados.gerado_em)}. {dados.aviso}
        </p>
      </section>
    </>
  );
}

export function MapaDoCafe({ pagina }: { pagina: PaginaDoApp }) {
  const [tipo, setTipo] = useState("arabica");
  const parametros = useMemo(() => ({ tipo }), [tipo]);
  const pedido = usarPedido<MapaDoCafeV1>(pagina.contrato?.rota ?? "", parametros);
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      <fieldset className="escolha-do-tipo">
        <legend>Café</legend>
        {TIPOS.map((t) => (
          <label key={t.valor}>
            <input type="radio" name="tipo" value={t.valor} checked={tipo === t.valor} onChange={() => setTipo(t.valor)} />
            {t.nome}
          </label>
        ))}
      </fieldset>
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Montando o mapa…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Resultado key={pedido.dados.tipo} dados={pedido.dados} />
      )}
    </section>
  );
}
