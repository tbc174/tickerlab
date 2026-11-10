// Encontrar empresas (tela do analista, linha 798): o analista escolhe o setor (seção do CNAE do IBGE), o
// estado e a idade mínima e vê as empresas ativas (a matriz, uma linha por empresa), cada uma com o link para a
// ficha, e baixa a lista em Excel. A rota usa o mesmo leitor e o mesmo portão da API externa: o que a API
// negaria não aparece aqui. As opções do formulário vêm da API (um pedido sem filtro, que não lê a base);
// "Limites e cuidados" fica sempre à vista depois da busca.
import { type FormEvent, useState } from "react";
import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import { CabecalhoDaTela } from "../CabecalhoDaTela";
import { ErroDaApi, baixar, pedir } from "../api";
import { Carregando } from "../Carregando";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import type { BuscaDeEmpresasV1, CampoComFonteV1, EmpresaDaBuscaV1, FonteDaFichaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const NOME_DA_PLANILHA = "empresas-tickerlab.xlsx";
const SETORES_MAXIMOS = 3; // o mesmo teto da rota (src/analista/busca.py)
const IDADE_MAXIMA = 100;
const SEM_FILTRO = {};
const SEM_VALOR = "—";
const CNPJ_SO_DIGITOS = /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/;
const FALHA = "Não deu agora. Tente de novo em instantes.";

export interface Filtros {
  setores: string[];
  ufs: string[];
  idade_minima?: number;
}

/** "02429144000193" → "02.429.144/0001-93"; outro formato sai como veio. */
const cnpjComPontuacao = (cnpj: string) => cnpj.replace(CNPJ_SO_DIGITOS, "$1.$2.$3/$4-$5");

const textoDe = (campo: CampoComFonteV1 | null) =>
  campo === null || campo.valor === null ? SEM_VALOR : String(campo.valor);

/** O código e, ao lado, o nome da Receita (o nome pode faltar: o código nunca some). */
const comNome = (campo: CampoComFonteV1 | null, nome: string | null) =>
  nome ? `${nome} (${textoDe(campo)})` : textoDe(campo);

function Empresas({ empresas }: { empresas: EmpresaDaBuscaV1[] }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela-do-app">
        <thead>
          <tr>
            <th scope="col">Empresa</th>
            <th scope="col">CNPJ</th>
            <th scope="col">Atividade principal</th>
            <th scope="col">Sede</th>
            <th scope="col">Aberta em</th>
            <th scope="col">Porte na Receita</th>
          </tr>
        </thead>
        <tbody>
          {empresas.map((empresa) => (
            <tr key={empresa.cnpj}>
              <th scope="row">
                {/* o CNPJ vai no estado da navegação, nunca no endereço */}
                <Link to="/ficha-da-empresa" state={{ cnpj: empresa.cnpj }}>
                  {textoDe(empresa.razao_social)}
                </Link>
              </th>
              <td>{cnpjComPontuacao(empresa.cnpj)}</td>
              <td>{comNome(empresa.cnae_principal, empresa.cnae_descricao)}</td>
              <td>
                {empresa.municipio_nome ?? textoDe(empresa.municipio)} / {textoDe(empresa.uf)}
              </td>
              <td>
                {empresa.data_inicio_atividade?.valor
                  ? formatarData(String(empresa.data_inicio_atividade.valor))
                  : SEM_VALOR}
              </td>
              <td>{empresa.porte_descricao ?? textoDe(empresa.porte)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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

function Fontes({ fontes }: { fontes: FonteDaFichaV1[] }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="fontes-da-busca">
      <h2 id="fontes-da-busca">Fontes</h2>
      <ul>
        {fontes.map((fonte) => (
          <li key={fonte.fonte}>
            {fonte.atribuicao} <span className="apagado">({fonte.fonte}; licença: {fonte.licenca})</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Limites({ itens }: { itens: string[] }) {
  return (
    <section className="secao-do-relatorio" aria-labelledby="limites-da-busca">
      <h2 id="limites-da-busca">Limites e cuidados</h2>
      <ul>
        {itens.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function BaixarPlanilha({ rota, filtros }: { rota: string; filtros: Filtros }) {
  const token = useConta()?.token ?? null;
  const [baixando, setBaixando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const baixarAgora = () => {
    if (token === null) return;
    setBaixando(true);
    setFalha(null);
    baixar(`${rota}/planilha`, token, filtros)
      .then((arquivo) => {
        const endereco = URL.createObjectURL(arquivo);
        const ancora = document.createElement("a");
        ancora.href = endereco;
        ancora.download = NOME_DA_PLANILHA;
        ancora.click();
        URL.revokeObjectURL(endereco);
      })
      .catch((erro: unknown) => setFalha(erro instanceof ErroDaApi ? erro.message : FALHA))
      .finally(() => setBaixando(false));
  };
  return (
    <>
      <button type="button" className="botao" disabled={baixando} onClick={baixarAgora}>
        Baixar em Excel
      </button>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </>
  );
}

/** A primeira página veio pronta; "Carregar mais" pede a seguinte pelo cursor e junta embaixo. */
function Lista({ primeira, rota, filtros }: { primeira: BuscaDeEmpresasV1; rota: string; filtros: Filtros }) {
  const token = useConta()?.token ?? null;
  const [empresas, setEmpresas] = useState(primeira.empresas);
  const [cursor, setCursor] = useState(primeira.proximo_cursor);
  const [carregando, setCarregando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
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
  if (empresas.length === 0) {
    return (
      <p className="apagado" role="note">
        Nenhuma empresa com esses filtros.
      </p>
    );
  }
  return (
    <>
      <p>
        {empresas.length} {empresas.length === 1 ? "empresa" : "empresas"}
        {cursor === null ? "" : " até aqui"}
        <span className="apagado"> · como a base conhecia em {formatarData(primeira.como_era_em ?? "")}</span>
      </p>
      <BaixarPlanilha rota={rota} filtros={filtros} />
      <Empresas empresas={empresas} />
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
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  const dados = pedido.dados;
  return (
    <>
      {dados.estado === "nao_liberada" ? (
        <p className="apagado" role="note">
          Dado ainda não liberado: a busca entra nesta tela quando a conferência da tabela terminar.
        </p>
      ) : (
        <Lista primeira={dados} rota={rota} filtros={filtros} />
      )}
      {dados.fontes.length > 0 ? <Fontes fontes={dados.fontes} /> : null}
      <Limites itens={dados.limites} />
    </>
  );
}

function alternar(lista: string[], item: string): string[] {
  return lista.includes(item) ? lista.filter((x) => x !== item) : [...lista, item];
}

function Formulario({ opcoes, aoBuscar }: { opcoes: BuscaDeEmpresasV1; aoBuscar: (filtros: Filtros) => void }) {
  const [setores, setSetores] = useState<string[]>([]);
  const [ufs, setUfs] = useState<string[]>([]);
  const [idade, setIdade] = useState("");
  const vazio = setores.length === 0 && ufs.length === 0 && idade === "";
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (vazio) return;
    aoBuscar({ setores, ufs, ...(idade === "" ? {} : { idade_minima: Number(idade) }) });
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
      <button className="botao primario" type="submit" disabled={vazio}>
        Encontrar empresas
      </button>
    </form>
  );
}

export function EncontrarEmpresas({ pagina }: { pagina: PaginaDoApp }) {
  const rota = pagina.contrato?.rota ?? "";
  const opcoes = usarPedido<BuscaDeEmpresasV1>(rota, {}, SEM_FILTRO);
  const [buscado, setBuscado] = useState<{ filtros: Filtros; vez: number } | null>(null);
  return (
    <section>
      <CabecalhoDaTela pagina={pagina} />
      {opcoes.estado === "carregando" && <Carregando tipo="painel" rotulo="Abrindo o formulário…" />}
      {opcoes.estado === "erro" && <ErroDaTela erro={opcoes.erro} />}
      {opcoes.estado === "pronto" && (
        <Formulario opcoes={opcoes.dados} aoBuscar={(filtros) => setBuscado({ filtros, vez: (buscado?.vez ?? 0) + 1 })} />
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
