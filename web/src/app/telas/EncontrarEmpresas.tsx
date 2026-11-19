// Encontrar empresas (tela do analista, linha 798): o analista escolhe o setor (seção do CNAE do IBGE), o
// estado, a idade mínima, o capital social e os estabelecimentos ativos (só uma aproximação do tamanho: nenhum
// dos dois mede faturamento) e vê as empresas ativas (a matriz, uma linha por empresa), cada uma com o link para a
// ficha, e baixa a lista em Excel. A rota usa o mesmo leitor e o mesmo portão da API externa: o que a API
// negaria não aparece aqui. As opções do formulário vêm da API (um pedido sem filtro, que não lê a base);
// "Limites e cuidados" fica sempre à vista depois da busca.
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
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
import { useEstadoDaNavegacaoUmaVez } from "../estadoDaNavegacao";
import { secaoDoCnae } from "../secaoDoCnae";
import type { BuscaDeEmpresasV1, CampoComFonteV1, EmpresaDaBuscaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { Erro } from "../pecas/Erro";
import { CaixaDeSugestoes } from "../pecas/CaixaDeSugestoes";
import { useAtividadesDoCnae } from "../pecas/CampoDoSetor";
import { type SecaoDaBusca, sugestoesDeSecao } from "../buscaDeSecoes";

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
// o capital das etiquetas, curto ("R$ 5 mi"): a etiqueta é um rótulo, o valor exato fica na tabela e no Excel
const REAIS_CURTO = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});
const CNAE_DO_SETOR = /^(\d{5}|\d{7})$/;
const DICA_DO_SETOR =
  "Pelo nome do setor ou de uma atividade (farmácia, hospital). A busca usa a seção inteira do CNAE.";
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

/** O valor da etiqueta em reais, curto: "R$ 5 mi", "R$ 1,5 bi" (sem valor, nada). */
const reaisCurto = (valor: number | undefined) =>
  valor === undefined ? "" : REAIS_CURTO.format(valor).replace(/ /g, " "); // o Intl põe espaço que não quebra

/** O código e, ao lado, o nome da Receita (o nome pode faltar: o código nunca some). */
const comNome = (campo: CampoComFonteV1 | null, nome: string | null) =>
  nome ? `${nome} (${textoDe(campo)})` : textoDe(campo);

/** O nome da Receita ou, sem ele, o CNPJ: a caixa de escolha nunca fica sem nome próprio. */
const nomeOuCnpj = (empresa: EmpresaDaBuscaV1) =>
  empresa.razao_social?.valor ? String(empresa.razao_social.valor) : cnpjComPontuacao(empresa.cnpj);

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
            aria-label={`Escolher ${nomeOuCnpj(empresa)} para comparar`}
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

/** A ordem da lista, ao lado da contagem: trocar refaz a busca com os mesmos filtros (sem ordem, é pelo CNPJ). */
function OrdemDaLista({ filtros, ordens, aoOrdenar }: { filtros: Filtros; ordens: BuscaDeEmpresasV1["ordens"]; aoOrdenar: Ordenar }) {
  return (
    <label className="ordem-da-lista">
      <span>Ordenar por</span>
      <select value={filtros.ordem ?? ""} onChange={(ev) => aoOrdenar(ev.target.value === "" ? undefined : ev.target.value)}>
        <option value="">Número do CNPJ</option>
        {ordens.map((opcao) => (
          <option key={opcao.codigo} value={opcao.codigo}>
            {opcao.nome}
          </option>
        ))}
      </select>
    </label>
  );
}

type Ordenar = (ordem: string | undefined) => void;

/** A primeira página veio pronta; "Carregar mais" pede a seguinte pelo cursor e junta embaixo. */
function Lista({
  primeira,
  rota,
  filtros,
  aoOrdenar,
}: {
  primeira: BuscaDeEmpresasV1;
  rota: string;
  filtros: Filtros;
  aoOrdenar: Ordenar;
}) {
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
      <div className="cabeca-da-lista">
        <p>
          <strong>
            {empresas.length} {empresas.length === 1 ? "empresa" : "empresas"}
          </strong>
          {cursor === null ? "" : " até aqui"}
          <span className="apagado"> · como a base conhecia em {formatarData(primeira.como_era_em ?? "")}</span>
        </p>
        <OrdemDaLista filtros={filtros} ordens={primeira.ordens} aoOrdenar={aoOrdenar} />
      </div>
      <Baixar rotulo="Baixar em Excel" rota={`${rota}/planilha`} corpo={filtros} nome={NOME_DA_PLANILHA} />
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
      <BandejaDeComparacao escolhidas={escolhidas} aoLimpar={() => setEscolhidas([])} />
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

function Resultado({ rota, filtros, aoOrdenar }: { rota: string; filtros: Filtros; aoOrdenar: Ordenar }) {
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
          <Lista primeira={dados} rota={rota} filtros={filtros} aoOrdenar={aoOrdenar} />
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

/** O resumo do estado escolhido, no botão da lista: "Brasil inteiro", "SP" ou "SP, MG". */
const resumoDosEstados = (ufs: string[]) => (ufs.length === 0 ? "Brasil inteiro" : ufs.join(", "));

/** O setor: uma caixa de busca nas seções do CNAE (pelo nome delas ou pelo de uma atividade) e, embaixo, as
 * escolhidas como etiquetas que se tiram com um clique. */
function SetoresDaBusca({
  secoes,
  escolhidas,
  aoMudar,
}: {
  secoes: SecaoDaBusca[];
  escolhidas: string[];
  aoMudar: (setores: string[]) => void;
}) {
  const atividades = useAtividadesDoCnae();
  const [texto, setTexto] = useState("");
  const cheio = escolhidas.length >= SETORES_MAXIMOS;
  const nomeDe = (codigo: string) => secoes.find((s) => s.codigo === codigo)?.nome ?? codigo;
  const sugestoes = (digitado: string) =>
    sugestoesDeSecao(secoes, atividades, digitado, escolhidas).map(({ secao, pelaAtividade }) => ({
      chave: secao.codigo,
      nome: secao.nome,
      detalhe: pelaAtividade ? `pela atividade: ${pelaAtividade}` : undefined,
    }));
  const escolher = (codigo: string) => {
    setTexto("");
    aoMudar([...escolhidas, codigo]);
  };
  return (
    <div className="setores-da-busca">
      <CaixaDeSugestoes
        rotulo={`Setor (até ${SETORES_MAXIMOS})`}
        texto={texto}
        sugestoes={sugestoes}
        rotuloDaLista="Setores"
        placeholder={cheio ? `Já são ${SETORES_MAXIMOS} setores` : "Ex.: comércio, saúde, farmácia"}
        dica={DICA_DO_SETOR}
        desligada={cheio}
        aoDigitar={setTexto}
        aoEscolher={escolher}
      />
      {escolhidas.length > 0 ? (
        <ul className="etiquetas-de-filtro" aria-label="Setores escolhidos">
          {escolhidas.map((codigo) => (
            <li key={codigo}>
              <button
                type="button"
                className="botao"
                aria-label={`Tirar o setor ${nomeDe(codigo)}`}
                onClick={() => aoMudar(escolhidas.filter((c) => c !== codigo))}
              >
                {nomeDe(codigo)} ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Fecha um <details> quando se clica fora dele ou se tecla Esc, como uma lista de escolha comum. */
function useFechaAoSair() {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const fechar = (evento: Event) => {
      const caixa = ref.current;
      if (!caixa?.open) return;
      const fora = evento instanceof KeyboardEvent ? evento.key === "Escape" : !caixa.contains(evento.target as Node);
      if (fora) caixa.open = false;
    };
    document.addEventListener("mousedown", fechar);
    document.addEventListener("keydown", fechar);
    return () => {
      document.removeEventListener("mousedown", fechar);
      document.removeEventListener("keydown", fechar);
    };
  }, []);
  return ref;
}

/** O estado da sede: uma lista que abre e fecha, com o resumo do que está escolhido ("Brasil inteiro" sem nada). */
function EstadosDaBusca({ ufs, escolhidas, aoMudar }: { ufs: string[]; escolhidas: string[]; aoMudar: (ufs: string[]) => void }) {
  const lista = useFechaAoSair();
  return (
    <fieldset className="estados-da-busca">
      <legend>Estado da sede</legend>
      <details className="lista-que-abre" ref={lista}>
        <summary>{resumoDosEstados(escolhidas)}</summary>
        <div className="grade-de-estados">
          {ufs.map((uf) => (
            <label key={uf}>
              <input type="checkbox" checked={escolhidas.includes(uf)} onChange={() => aoMudar(alternar(escolhidas, uf))} />
              {uf}
            </label>
          ))}
        </div>
      </details>
    </fieldset>
  );
}

/** Faixas prontas de capital social: um clique preenche o mínimo e o máximo (e ainda dá para digitar o valor). */
const FAIXAS_DE_CAPITAL: { rotulo: string; minimo: string; maximo: string }[] = [
  { rotulo: "Até R$ 1 mi", minimo: "", maximo: "1000000" },
  { rotulo: "R$ 1 mi a 10 mi", minimo: "1000000", maximo: "10000000" },
  { rotulo: "R$ 10 mi a 100 mi", minimo: "10000000", maximo: "100000000" },
  { rotulo: "Acima de R$ 100 mi", minimo: "100000000", maximo: "" },
];

/** O formulário parte dos filtros da busca em curso: tirar uma etiqueta desmarca o campo aqui também. O essencial
 * (setor, estado e o botão) fica numa linha; idade, capital e estabelecimentos ficam em "Mais filtros", aberto só
 * quando um deles está em uso. A ordem fica ao lado da lista, não aqui. */
function Formulario({
  opcoes,
  inicial,
  comBusca,
  aoBuscar,
  aoLimpar,
}: {
  opcoes: BuscaDeEmpresasV1;
  inicial: Filtros | null;
  comBusca: boolean;
  aoBuscar: (filtros: Filtros) => void;
  aoLimpar: () => void;
}) {
  const [setores, setSetores] = useState<string[]>(inicial?.setores ?? []);
  const [ufs, setUfs] = useState<string[]>(inicial?.ufs ?? []);
  const [idade, setIdade] = useState(textoDoNumero(inicial?.idade_minima));
  const [capitalMinimo, setCapitalMinimo] = useState(textoDoNumero(inicial?.capital_minimo));
  const [capitalMaximo, setCapitalMaximo] = useState(textoDoNumero(inicial?.capital_maximo));
  const [estabelecimentos, setEstabelecimentos] = useState(textoDoNumero(inicial?.estabelecimentos_minimo));
  const numeros = [idade, capitalMinimo, capitalMaximo, estabelecimentos];
  const emUsoNoMais = numeros.filter((n) => n !== "").length;
  const vazio = setores.length === 0 && ufs.length === 0 && emUsoNoMais === 0;
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
        ordem: inicial?.ordem, // a ordem escolhida ao lado da lista continua na busca nova
      }),
    );
  };
  return (
    <form className="formulario-do-app" onSubmit={enviar}>
      <div className="linha-essencial">
        <SetoresDaBusca secoes={opcoes.setores} escolhidas={setores} aoMudar={setSetores} />
        <EstadosDaBusca ufs={opcoes.ufs} escolhidas={ufs} aoMudar={setUfs} />
        <div className="botoes-da-busca">
          <button className="botao primario" type="submit" disabled={vazio}>
            Encontrar empresas
          </button>
          <button className="botao" type="button" disabled={vazio && !comBusca} onClick={aoLimpar}>
            Limpar filtros
          </button>
        </div>
      </div>
      <details className="opcoes-avancadas mais-filtros" open={emUsoNoMais > 0}>
        <summary>Mais filtros{emUsoNoMais > 0 ? ` (${emUsoNoMais} em uso)` : ""}</summary>
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
        </div>
        <fieldset className="capital-da-busca">
          <legend>Capital social</legend>
          <div className="faixas-de-capital" role="group" aria-label="Faixas de capital social">
            {FAIXAS_DE_CAPITAL.map((faixa) => (
              <button
                key={faixa.rotulo}
                type="button"
                className="botao"
                aria-pressed={capitalMinimo === faixa.minimo && capitalMaximo === faixa.maximo}
                onClick={() => {
                  setCapitalMinimo(faixa.minimo);
                  setCapitalMaximo(faixa.maximo);
                }}
              >
                {faixa.rotulo}
              </button>
            ))}
          </div>
          <div className="campos-do-formulario">
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
          </div>
        </fieldset>
        <p className="apagado">{APROXIMACAO}</p>
      </details>
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
    ...numero("capital_minimo", `Capital social mínimo: ${reaisCurto(filtros.capital_minimo)}`, filtros.capital_minimo),
    ...numero("capital_maximo", `Capital social máximo: ${reaisCurto(filtros.capital_maximo)}`, filtros.capital_maximo),
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

/** O que o Setor manda ao abrir esta tela: o filtro já pronto (se o CNAE tem seção nesta busca) e a nota que diz
 * de onde ele veio e por que a busca é mais ampla que o CNAE. */
export interface AberturaDoSetor {
  filtros: Filtros | null;
  nota: string;
}

/** O pedido que o Setor guardou no estado da navegação (o CNAE e a UF, nunca no endereço): só vale se o CNAE é de
 * uma divisão do CNAE; o resto do estado se ignora. A busca filtra pela seção do CNAE, e só entra o que o formulário
 * oferece (a seção fora da busca e a UF desconhecida ficam de fora, com a nota dizendo). */
export function aberturaDoSetor(estado: unknown, opcoes: BuscaDeEmpresasV1): AberturaDoSetor | null {
  if (typeof estado !== "object" || estado === null || !("doSetor" in estado)) return null;
  const pedido = estado.doSetor;
  if (typeof pedido !== "object" || pedido === null || !("cnae" in pedido)) return null;
  const { cnae } = pedido;
  if (typeof cnae !== "string" || !CNAE_DO_SETOR.test(cnae)) return null;
  const secao = secaoDoCnae(cnae);
  if (secao === null) return null;
  const uf = "uf" in pedido && typeof pedido.uf === "string" && opcoes.ufs.includes(pedido.uf) ? pedido.uf : null;
  const setor = opcoes.setores.find((s) => s.codigo === secao);
  const filtros: Filtros = { setores: setor ? [secao] : [], ufs: uf ? [uf] : [] };
  const onde = uf ? ` em ${uf}` : "";
  const nota = setor
    ? `Aberto a partir do CNAE ${cnae}${onde}: esta busca filtra pela seção do CNAE, ${setor.nome}, que é mais ampla do que o CNAE.`
    : `Aberto a partir do CNAE ${cnae}${onde}: a seção dele não está nesta busca.${uf ? " Só o estado entrou no filtro." : " Nenhum filtro foi aplicado."}`;
  return { filtros: temFiltro(filtros) ? filtros : null, nota };
}

/** O setor e o estado que chegam no endereço (o link dos cruzamentos do site, linha 925): só `setor` e `uf`,
 * um de cada, e só valores que o formulário oferece; o resto se ignora, sem erro, e sem nenhum dos dois a
 * tela abre com o filtro vazio. */
export function filtrosDoEndereco(busca: URLSearchParams, opcoes: BuscaDeEmpresasV1): Filtros | null {
  const setor = busca.get("setor");
  const uf = busca.get("uf");
  const filtros: Filtros = {
    setores: setor !== null && opcoes.setores.some((s) => s.codigo === setor) ? [setor] : [],
    ufs: uf !== null && opcoes.ufs.includes(uf) ? [uf] : [],
  };
  return temFiltro(filtros) ? filtros : null;
}

/** O filtro com que a busca começa: o que o Setor mandou vale primeiro (um clique de dentro do app, que vale uma vez
 * só), mesmo sem filtro, porque a nota dele diz o que entrou; sem ele, o do endereço. */
export function filtroInicial(abertura: AberturaDoSetor | null, doEndereco: Filtros | null): Filtros | null {
  return abertura ? abertura.filtros : doEndereco;
}

const AVISO_DE_COMECO = (
  <p className="apagado">
    Escolha ao menos um filtro. Aparecem só empresas com cadastro ativo na Receita Federal, uma linha por empresa;
    pessoa física, MEI e empresário individual não aparecem. Nada aqui é recomendação de investimento.
  </p>
);

// buscas de exemplo para a tela vazia: um clique e a lista aparece, com o formulário mostrando os filtros
const EXEMPLOS: Filtros[] = [
  { setores: ["G"], ufs: ["SP"] },
  { setores: ["C"], ufs: ["MG"], idade_minima: 20 },
  { setores: ["J"], ufs: [], capital_minimo: 10_000_000 },
];

/** "Indústrias de transformação em MG, com 20 anos ou mais"; null se o exemplo usa setor ou estado que a busca não
 * oferece (o exemplo some, em vez de dar erro). */
export function descricaoDoExemplo(filtros: Filtros, opcoes: BuscaDeEmpresasV1): string | null {
  const nomes = filtros.setores.map((codigo) => opcoes.setores.find((s) => s.codigo === codigo)?.nome);
  if (nomes.some((n) => n === undefined) || filtros.ufs.some((uf) => !opcoes.ufs.includes(uf))) return null;
  const onde = filtros.ufs.length > 0 ? ` em ${filtros.ufs.join(", ")}` : "";
  const extras = [
    filtros.idade_minima === undefined ? null : `com ${filtros.idade_minima} anos ou mais`,
    filtros.capital_minimo === undefined ? null : `com capital social a partir de ${reaisCurto(filtros.capital_minimo)}`,
  ].filter((e) => e !== null);
  return `${nomes.join(", ")}${onde}${extras.length > 0 ? `, ${extras.join(", ")}` : ""}`;
}

/** A tela antes da primeira busca: os exemplos que se clicam e o aviso de quem aparece na lista. */
function ComecoDaBusca({ opcoes, aoBuscar }: { opcoes: BuscaDeEmpresasV1; aoBuscar: (filtros: Filtros) => void }) {
  const exemplos = EXEMPLOS.map((filtros) => ({ filtros, descricao: descricaoDoExemplo(filtros, opcoes) })).filter(
    (e): e is { filtros: Filtros; descricao: string } => e.descricao !== null,
  );
  return (
    <>
      {exemplos.length > 0 ? (
        <section className="exemplos-de-busca" aria-label="Exemplos de busca">
          <p>Para começar, experimente uma destas buscas:</p>
          <ul>
            {exemplos.map((exemplo) => (
              <li key={exemplo.descricao}>
                <button type="button" className="botao" onClick={() => aoBuscar(exemplo.filtros)}>
                  {exemplo.descricao}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {AVISO_DE_COMECO}
    </>
  );
}

/** O formulário, as etiquetas e a lista, depois que as opções chegaram; a busca já começa com o filtro que o Setor
 * mandou ou, sem ele, com o do endereço, se houver. */
function Busca({
  rota,
  opcoes,
  abertura,
  doEndereco,
}: {
  rota: string;
  opcoes: BuscaDeEmpresasV1;
  abertura: AberturaDoSetor | null;
  doEndereco: Filtros | null;
}) {
  const inicial = filtroInicial(abertura, doEndereco);
  const [buscado, setBuscado] = useState<{ filtros: Filtros; vez: number } | null>(
    inicial ? { filtros: inicial, vez: 1 } : null,
  );
  const [vezDoFormulario, setVezDoFormulario] = useState(0);
  const [comNota, setComNota] = useState(true);
  // buscar de novo (formulário ou etiqueta) abre uma lista nova, sem a escolha da lista anterior
  const buscarDe = (filtros: Filtros | null) => {
    setBuscado(filtros === null ? null : { filtros, vez: (buscado?.vez ?? 0) + 1 });
    setVezDoFormulario((v) => v + 1);
  };
  const limpar = () => {
    setComNota(false); // a nota fala do filtro que veio do Setor: sem ele, não há o que explicar
    buscarDe(null);
  };
  return (
    <>
      {abertura && comNota ? (
        <p className="apagado" role="note">
          {abertura.nota}
        </p>
      ) : null}
      <Formulario
        key={vezDoFormulario}
        opcoes={opcoes}
        inicial={buscado?.filtros ?? null}
        comBusca={buscado !== null}
        aoBuscar={buscarDe}
        aoLimpar={limpar}
      />
      {buscado === null ? (
        <ComecoDaBusca opcoes={opcoes} aoBuscar={buscarDe} />
      ) : (
        <>
          <EtiquetasDeFiltro filtros={buscado.filtros} opcoes={opcoes} aoMudar={buscarDe} />
          <Resultado
            key={buscado.vez}
            rota={rota}
            filtros={buscado.filtros}
            aoOrdenar={(ordem) => buscarDe(semVazios({ ...buscado.filtros, ordem }))}
          />
        </>
      )}
    </>
  );
}

export function EncontrarEmpresas({ pagina }: { pagina: PaginaDoApp }) {
  const rota = pagina.contrato?.rota ?? "";
  const opcoes = usarPedido<BuscaDeEmpresasV1>(rota, {}, SEM_FILTRO);
  const doSetor = useEstadoDaNavegacaoUmaVez(); // o CNAE e a UF do Setor valem uma vez só, como o CNPJ da ficha
  const [endereco] = useSearchParams();
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {opcoes.estado === "carregando" && <Carregando tipo="painel" rotulo="Abrindo o formulário…" />}
      {opcoes.estado === "erro" && <Erro erro={opcoes.erro} />}
      {opcoes.estado === "pronto" ? (
        <Busca
          rota={rota}
          opcoes={opcoes.dados}
          abertura={aberturaDoSetor(doSetor, opcoes.dados)}
          doEndereco={filtrosDoEndereco(endereco, opcoes.dados)}
        />
      ) : (
        AVISO_DE_COMECO
      )}
    </section>
  );
}
