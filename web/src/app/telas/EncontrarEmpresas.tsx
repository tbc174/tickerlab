// Encontrar empresas (tela do analista, linha 798): o analista escolhe o setor (seção do CNAE do IBGE), o
// estado, a idade mínima, o capital social e os estabelecimentos ativos (só uma aproximação do tamanho: nenhum
// dos dois mede faturamento) e vê as empresas ativas (a matriz, uma linha por empresa), cada uma com o link para a
// ficha, e baixa a lista em Excel. A rota usa o mesmo leitor e o mesmo portão da API externa: o que a API
// negaria não aparece aqui. As opções do formulário vêm da API (um pedido sem filtro, que não lê a base);
// "Limites e cuidados" fica sempre à vista depois da busca.
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../pecas/Cabecalho";
import { ErroDaApi, pedir } from "../api";
import { Baixar } from "../pecas/Baixar";
import { Fontes } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import { type Coluna, Tabela } from "../pecas/Tabela";
import { Vazio } from "../pecas/Vazio";
import { Carregando } from "../pecas/Carregando";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import type { BuscaDeEmpresasV1, CampoComFonteV1, EmpresaDaBuscaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { Erro } from "../pecas/Erro";

const NOME_DA_PLANILHA = "empresas-tickerlab.xlsx";
const MINIMO_NA_COMPARACAO = 2;
const MAXIMO_NA_COMPARACAO = 5; // o mesmo teto da tela Comparar empresas
const SETORES_MAXIMOS = 3; // o mesmo teto da rota (src/analista/busca.py)
const IDADE_MAXIMA = 100;
const SEM_FILTRO = {};
const SEM_VALOR = "—";
const CNPJ_SO_DIGITOS = /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/;
const FALHA = "Não deu agora. Tente de novo em instantes.";
const REAIS = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const APROXIMACAO =
  "Capital social e estabelecimentos ativos são só uma aproximação do tamanho: nenhum dos dois mede faturamento.";

export interface Filtros {
  setores: string[];
  ufs: string[];
  idade_minima?: number;
  capital_minimo?: number;
  capital_maximo?: number;
  estabelecimentos_minimo?: number;
  ordem?: string;
}

/** "02429144000193" → "02.429.144/0001-93"; outro formato sai como veio. */
const cnpjComPontuacao = (cnpj: string) => cnpj.replace(CNPJ_SO_DIGITOS, "$1.$2.$3/$4-$5");

const textoDe = (campo: CampoComFonteV1 | null) =>
  campo === null || campo.valor === null ? SEM_VALOR : String(campo.valor);

/** O capital declarado em reais, sem centavos (o Excel leva o valor exato). */
const reaisDe = (campo: CampoComFonteV1 | null | undefined) =>
  typeof campo?.valor === "number" ? REAIS.format(campo.valor) : SEM_VALOR;

/** O código e, ao lado, o nome da Receita (o nome pode faltar: o código nunca some). */
const comNome = (campo: CampoComFonteV1 | null, nome: string | null) =>
  nome ? `${nome} (${textoDe(campo)})` : textoDe(campo);

/** A coluna de seleção + as colunas da lista. O CNPJ vai no estado da navegação, nunca no endereço. */
function colunasDaLista(
  selecionados: string[],
  alternarEmpresa: (empresa: EmpresaDaBuscaV1) => void,
): Coluna<EmpresaDaBuscaV1>[] {
  return [
    {
      chave: "escolher",
      titulo: "Comparar",
      celula: (empresa) => {
        const marcada = selecionados.includes(empresa.cnpj);
        return (
          <input
            type="checkbox"
            checked={marcada}
            disabled={!marcada && selecionados.length >= MAXIMO_NA_COMPARACAO}
            aria-label={`Escolher ${textoDe(empresa.razao_social)} para comparar`}
            onChange={() => alternarEmpresa(empresa)}
          />
        );
      },
    },
    {
      chave: "empresa",
      titulo: "Empresa",
      celula: (empresa) => (
        <Link to="/ficha-da-empresa" state={{ cnpj: empresa.cnpj }}>
          {textoDe(empresa.razao_social)}
        </Link>
      ),
    },
    { chave: "cnpj", titulo: "CNPJ", celula: (empresa) => cnpjComPontuacao(empresa.cnpj) },
    { chave: "atividade", titulo: "Atividade principal", celula: (e) => comNome(e.cnae_principal, e.cnae_descricao) },
    {
      chave: "sede",
      titulo: "Sede",
      celula: (e) => `${e.municipio_nome ?? textoDe(e.municipio)} / ${textoDe(e.uf)}`,
    },
    {
      chave: "aberta",
      titulo: "Aberta em",
      celula: (e) => (e.data_inicio_atividade?.valor ? formatarData(String(e.data_inicio_atividade.valor)) : SEM_VALOR),
    },
    { chave: "porte", titulo: "Porte na Receita", celula: (e) => e.porte_descricao ?? textoDe(e.porte) },
    { chave: "capital", titulo: "Capital social", numero: true, celula: (e) => reaisDe(e.capital_social) },
    {
      chave: "estabelecimentos",
      titulo: "Estabelecimentos ativos",
      numero: true,
      celula: (e) => textoDe(e.n_estabelecimentos ?? null),
    },
  ];
}

/** A fonte e o dia de publicação dos campos da página, uma vez cada (quase sempre um só). */
function DeOndeVem({ empresas }: { empresas: EmpresaDaBuscaV1[] }) {
  const campos = empresas.flatMap((e) =>
    Object.values(e).filter((v): v is CampoComFonteV1 => typeof v === "object" && v !== null && "fonte" in v),
  );
  const fontes = [...new Set(campos.map((c) => c.fonte))].join(", ");
  const datas = [...new Set(campos.map((c) => formatarData(c.publico_em)))].join(", ");
  return (
    <p className="apagado">
      Fonte: {fontes} · publicado em {datas}
    </p>
  );
}

/** A bandeja que acompanha a seleção: quais empresas, quantas faltam e o botão que leva à comparação. */
function BandejaDeComparacao({ escolhidas, aoLimpar }: { escolhidas: EmpresaDaBuscaV1[]; aoLimpar: () => void }) {
  const navegar = useNavigate();
  if (escolhidas.length === 0) return null;
  const pronta = escolhidas.length >= MINIMO_NA_COMPARACAO;
  return (
    <section className="bandeja-de-comparacao" aria-label="Comparar">
      <p>
        <strong>{escolhidas.length}</strong> {escolhidas.length === 1 ? "empresa escolhida" : "empresas escolhidas"}:{" "}
        {escolhidas.map((e) => textoDe(e.razao_social)).join(", ")}
        {pronta ? "" : ` · escolha ao menos mais ${MINIMO_NA_COMPARACAO - escolhidas.length}`}
      </p>
      {/* os CNPJs vão no estado da navegação, nunca no endereço */}
      <button
        type="button"
        className="botao primario"
        disabled={!pronta}
        onClick={() => navegar("/comparar-empresas", { state: { cnpjs: escolhidas.map((e) => e.cnpj) } })}
      >
        Comparar
      </button>{" "}
      <button type="button" className="botao" onClick={aoLimpar}>
        Limpar a escolha
      </button>
    </section>
  );
}

/** A primeira página veio pronta; "Carregar mais" pede a seguinte pelo cursor e junta embaixo. */
function Lista({ primeira, rota, filtros }: { primeira: BuscaDeEmpresasV1; rota: string; filtros: Filtros }) {
  const token = useConta()?.token ?? null;
  const [empresas, setEmpresas] = useState(primeira.empresas);
  const [cursor, setCursor] = useState(primeira.proximo_cursor);
  const [carregando, setCarregando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const [escolhidas, setEscolhidas] = useState<EmpresaDaBuscaV1[]>([]);
  const alternarEmpresa = (empresa: EmpresaDaBuscaV1) =>
    setEscolhidas((antes) =>
      antes.some((e) => e.cnpj === empresa.cnpj) ? antes.filter((e) => e.cnpj !== empresa.cnpj) : [...antes, empresa],
    );
  const carregarMais = () => {
    if (token === null || cursor === null) return;
    setCarregando(true);
    setFalha(null);
    pedir<BuscaDeEmpresasV1>(rota, token, {}, { ...filtros, cursor })
      .then((seguinte) => {
        setEmpresas((antes) => [...antes, ...seguinte.empresas]);
        setCursor(seguinte.proximo_cursor);
      })
      .catch((erro: unknown) => setFalha(erro instanceof ErroDaApi ? erro.message : FALHA))
      .finally(() => setCarregando(false));
  };
  if (empresas.length === 0) return <Vazio frase="Nenhuma empresa com esses filtros." />;
  return (
    <>
      <p>
        {empresas.length} {empresas.length === 1 ? "empresa" : "empresas"}
        {cursor === null ? "" : " até aqui"}
        <span className="apagado"> · como a base conhecia em {formatarData(primeira.como_era_em ?? "")}</span>
      </p>
      <Baixar rotulo="Baixar em Excel" rota={`${rota}/planilha`} corpo={filtros} nome={NOME_DA_PLANILHA} />
      <BandejaDeComparacao escolhidas={escolhidas} aoLimpar={() => setEscolhidas([])} />
      <Tabela
        legenda="Empresas encontradas"
        legendaEscondida
        colunas={colunasDaLista(
          escolhidas.map((e) => e.cnpj),
          alternarEmpresa,
        )}
        linhas={empresas}
        chaveDaLinha={(empresa) => empresa.cnpj}
      />
      <DeOndeVem empresas={empresas} />
      {cursor === null ? null : (
        <button type="button" className="botao" disabled={carregando} onClick={carregarMais}>
          Carregar mais
        </button>
      )}
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

function Resultado({ rota, filtros }: { rota: string; filtros: Filtros }) {
  const pedido = usarPedido<BuscaDeEmpresasV1>(rota, {}, filtros);
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Procurando empresas…" />;
  if (pedido.estado === "erro") return <Erro erro={pedido.erro} />;
  const dados = pedido.dados;
  return (
    <>
      {dados.estado === "nao_liberada" ? (
        <p className="apagado" role="note">
          Dado ainda não liberado: a busca entra nesta tela quando a conferência da tabela terminar.
        </p>
      ) : (
        <>
          {/* dado de piloto nunca aparece sem o aviso (D11.3): a frase vem do servidor */}
          {dados.aviso_de_piloto ? (
            <p className="erro-do-app" role="note">
              {dados.aviso_de_piloto}
            </p>
          ) : null}
          <Lista primeira={dados} rota={rota} filtros={filtros} />
        </>
      )}
      {dados.fontes.length > 0 ? <Fontes fontes={dados.fontes} /> : null}
      <Limites itens={dados.limites} />
    </>
  );
}

function alternar(lista: string[], item: string): string[] {
  return lista.includes(item) ? lista.filter((x) => x !== item) : [...lista, item];
}

/** O texto de um campo numérico vira número; vazio fica de fora do pedido. */
function numeroDe(texto: string): number | undefined {
  return texto === "" ? undefined : Number(texto);
}

/** Só as chaves escolhidas: o pedido não leva filtro vazio. */
function semVazios(filtros: Filtros): Filtros {
  return Object.fromEntries(Object.entries(filtros).filter(([, valor]) => valor !== undefined)) as unknown as Filtros;
}

const textoDoNumero = (n: number | undefined) => (n === undefined ? "" : String(n));

/** O formulário parte dos filtros da busca em curso: tirar uma etiqueta desmarca o campo aqui também. */
function Formulario({
  opcoes,
  inicial,
  aoBuscar,
}: {
  opcoes: BuscaDeEmpresasV1;
  inicial: Filtros | null;
  aoBuscar: (filtros: Filtros) => void;
}) {
  const [setores, setSetores] = useState<string[]>(inicial?.setores ?? []);
  const [ufs, setUfs] = useState<string[]>(inicial?.ufs ?? []);
  const [idade, setIdade] = useState(textoDoNumero(inicial?.idade_minima));
  const [capitalMinimo, setCapitalMinimo] = useState(textoDoNumero(inicial?.capital_minimo));
  const [capitalMaximo, setCapitalMaximo] = useState(textoDoNumero(inicial?.capital_maximo));
  const [estabelecimentos, setEstabelecimentos] = useState(textoDoNumero(inicial?.estabelecimentos_minimo));
  const [ordem, setOrdem] = useState(inicial?.ordem ?? "");
  // a ordem não filtra: sozinha, a busca leria a base inteira
  const numeros = [idade, capitalMinimo, capitalMaximo, estabelecimentos];
  const vazio = setores.length === 0 && ufs.length === 0 && numeros.every((n) => n === "");
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (vazio) return;
    aoBuscar(
      semVazios({
        setores,
        ufs,
        idade_minima: numeroDe(idade),
        capital_minimo: numeroDe(capitalMinimo),
        capital_maximo: numeroDe(capitalMaximo),
        estabelecimentos_minimo: numeroDe(estabelecimentos),
        ordem: ordem === "" ? undefined : ordem,
      }),
    );
  };
  return (
    <form className="formulario-do-app" onSubmit={enviar}>
      <fieldset className="escolha-do-tipo">
        <legend>Setor (até {SETORES_MAXIMOS})</legend>
        {opcoes.setores.map((setor) => (
          <label key={setor.codigo}>
            <input
              type="checkbox"
              checked={setores.includes(setor.codigo)}
              disabled={!setores.includes(setor.codigo) && setores.length >= SETORES_MAXIMOS}
              onChange={() => setSetores((antes) => alternar(antes, setor.codigo))}
            />
            {setor.nome}
          </label>
        ))}
      </fieldset>
      <fieldset className="escolha-do-tipo">
        <legend>Estado da sede</legend>
        {opcoes.ufs.map((uf) => (
          <label key={uf}>
            <input type="checkbox" checked={ufs.includes(uf)} onChange={() => setUfs((antes) => alternar(antes, uf))} />
            {uf}
          </label>
        ))}
      </fieldset>
      <div className="campos-do-formulario">
        <label>
          <span>Idade mínima (anos)</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={IDADE_MAXIMA}
            value={idade}
            onChange={(ev) => setIdade(ev.target.value)}
          />
        </label>
      </div>
      <fieldset className="campos-do-formulario">
        <legend>Tamanho</legend>
        <p className="apagado">{APROXIMACAO}</p>
        <label>
          <span>Capital social mínimo (R$)</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            value={capitalMinimo}
            onChange={(ev) => setCapitalMinimo(ev.target.value)}
          />
        </label>
        <label>
          <span>Capital social máximo (R$)</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            value={capitalMaximo}
            onChange={(ev) => setCapitalMaximo(ev.target.value)}
          />
        </label>
        <label>
          <span>Estabelecimentos ativos, no mínimo</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            value={estabelecimentos}
            onChange={(ev) => setEstabelecimentos(ev.target.value)}
          />
        </label>
        <label>
          <span>Ordenar por</span>
          <select value={ordem} onChange={(ev) => setOrdem(ev.target.value)}>
            <option value="">Número do CNPJ</option>
            {opcoes.ordens.map((opcao) => (
              <option key={opcao.codigo} value={opcao.codigo}>
                {opcao.nome}
              </option>
            ))}
          </select>
        </label>
      </fieldset>
      <button className="botao primario" type="submit" disabled={vazio}>
        Encontrar empresas
      </button>
    </form>
  );
}

/** Uma etiqueta por filtro em uso: o rótulo e como ficam os filtros sem ele. */
interface Etiqueta {
  chave: string;
  rotulo: string;
  semEla: Filtros;
}

function etiquetasDosFiltros(filtros: Filtros, opcoes: BuscaDeEmpresasV1): Etiqueta[] {
  const nomeDoSetor = (codigo: string) => opcoes.setores.find((s) => s.codigo === codigo)?.nome ?? codigo;
  const sem = (campos: Partial<Filtros>) => semVazios({ ...filtros, ...campos });
  const numero = (chave: keyof Filtros, rotulo: string, valor: number | undefined): Etiqueta[] =>
    valor === undefined ? [] : [{ chave, rotulo, semEla: sem({ [chave]: undefined }) }];
  return [
    ...filtros.setores.map((codigo) => ({
      chave: `setor-${codigo}`,
      rotulo: `Setor: ${nomeDoSetor(codigo)}`,
      semEla: sem({ setores: filtros.setores.filter((c) => c !== codigo) }),
    })),
    ...filtros.ufs.map((uf) => ({
      chave: `uf-${uf}`,
      rotulo: `Estado: ${uf}`,
      semEla: sem({ ufs: filtros.ufs.filter((u) => u !== uf) }),
    })),
    ...numero("idade_minima", `Idade mínima: ${filtros.idade_minima} anos`, filtros.idade_minima),
    ...numero("capital_minimo", `Capital social mínimo: ${filtros.capital_minimo}`, filtros.capital_minimo),
    ...numero("capital_maximo", `Capital social máximo: ${filtros.capital_maximo}`, filtros.capital_maximo),
    ...numero(
      "estabelecimentos_minimo",
      `Estabelecimentos ativos, no mínimo: ${filtros.estabelecimentos_minimo}`,
      filtros.estabelecimentos_minimo,
    ),
  ];
}

/** A busca precisa de ao menos um filtro de verdade (a ordem sozinha leria a base inteira). */
const temFiltro = (f: Filtros) =>
  f.setores.length > 0 ||
  f.ufs.length > 0 ||
  [f.idade_minima, f.capital_minimo, f.capital_maximo, f.estabelecimentos_minimo].some((n) => n !== undefined);

/** Os filtros em uso como etiquetas que se tiram com um clique; a busca se refaz sem o filtro tirado. */
function EtiquetasDeFiltro({
  filtros,
  opcoes,
  aoMudar,
}: {
  filtros: Filtros;
  opcoes: BuscaDeEmpresasV1;
  aoMudar: (filtros: Filtros | null) => void;
}) {
  const etiquetas = etiquetasDosFiltros(filtros, opcoes);
  if (etiquetas.length === 0) return null;
  return (
    <ul className="etiquetas-de-filtro" aria-label="Filtros em uso">
      {etiquetas.map((etiqueta) => (
        <li key={etiqueta.chave}>
          <button
            type="button"
            className="botao"
            aria-label={`Tirar o filtro ${etiqueta.rotulo}`}
            onClick={() => aoMudar(temFiltro(etiqueta.semEla) ? etiqueta.semEla : null)}
          >
            {etiqueta.rotulo} ×
          </button>
        </li>
      ))}
    </ul>
  );
}

export function EncontrarEmpresas({ pagina }: { pagina: PaginaDoApp }) {
  const rota = pagina.contrato?.rota ?? "";
  const opcoes = usarPedido<BuscaDeEmpresasV1>(rota, {}, SEM_FILTRO);
  const [buscado, setBuscado] = useState<{ filtros: Filtros; vez: number } | null>(null);
  const [vezDoFormulario, setVezDoFormulario] = useState(0);
  // buscar de novo (formulário ou etiqueta) abre uma lista nova, sem a escolha da lista anterior
  const buscarDe = (filtros: Filtros | null) => {
    setBuscado(filtros === null ? null : { filtros, vez: (buscado?.vez ?? 0) + 1 });
    setVezDoFormulario((v) => v + 1);
  };
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {opcoes.estado === "carregando" && <Carregando tipo="painel" rotulo="Abrindo o formulário…" />}
      {opcoes.estado === "erro" && <Erro erro={opcoes.erro} />}
      {opcoes.estado === "pronto" && (
        <>
          <Formulario
            key={vezDoFormulario}
            opcoes={opcoes.dados}
            inicial={buscado?.filtros ?? null}
            aoBuscar={buscarDe}
          />
          {buscado === null ? null : (
            <EtiquetasDeFiltro filtros={buscado.filtros} opcoes={opcoes.dados} aoMudar={buscarDe} />
          )}
        </>
      )}
      {buscado === null ? (
        <p className="apagado">
          Escolha ao menos um filtro. Aparecem só empresas com cadastro ativo na Receita Federal, uma linha por
          empresa; pessoa física, MEI e empresário individual não aparecem. Nada aqui é recomendação de
          investimento.
        </p>
      ) : (
        <Resultado key={buscado.vez} rota={rota} filtros={buscado.filtros} />
      )}
    </section>
  );
}
