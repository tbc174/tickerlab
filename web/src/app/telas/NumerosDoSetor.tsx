// Os números do setor (linha 903, tela de Setor): empresas ativas, por UF e aberturas por ano de um CNAE, só
// contagens e só pessoa jurídica (MEI e empresário individual não entram, dito à vista). Bloco que o portão não
// libera diz "Não consultado", nunca zero. O CNAE vai no corpo do POST, nunca no endereço.
import { Link } from "react-router";
import { Carregando } from "../pecas/Carregando";
import { CartaoDeNumero } from "../pecas/CartaoDeNumero";
import { Erro } from "../pecas/Erro";
import { Fonte } from "../pecas/Fonte";
import { Tabela, type Coluna } from "../pecas/Tabela";
import { Vazio } from "../pecas/Vazio";
import { formatarData, formatarMes } from "../formatar";
import type { AberturasPorAnoV1, EmpresasPorUfV1, PerfilDoSetorV1 } from "../tipos";
import { usarPedido } from "../usarPedido";

const ROTA = "/v1/analista/setor/perfil";
const MILHAR = new Intl.NumberFormat("pt-BR");
const NAO_CONSULTADO = "Não consultado nesta base. Isto não quer dizer que o setor não tenha empresas.";

const ROTA_DO_EXPLORAR = "/encontrar-empresas";

/** O link que abre o Explorar já no setor: o CNAE e a UF vão no estado da navegação, nunca no endereço. */
function VerAsEmpresas({ cnae, uf, rotulo, texto }: { cnae: string; uf: string | null; rotulo: string; texto: string }) {
  return (
    <Link to={ROTA_DO_EXPLORAR} state={{ doSetor: { cnae, uf } }} aria-label={rotulo}>
      {texto}
    </Link>
  );
}

/** As colunas da tabela por UF: a barra (só desenho, escondida de quem lê por voz: o número está na coluna ao
 * lado), o número e o caminho para as empresas daquela UF. */
const colunasDaUf = (cnae: string, maior: number): Coluna<EmpresasPorUfV1>[] => [
  {
    chave: "uf",
    titulo: "UF",
    celula: (u) => (
      <span className="uf-com-barra">
        <span>{u.uf}</span>
        <span className="trilho-da-uf" aria-hidden="true">
          <span className="barra-da-uf" style={{ width: `${Math.max(1, Math.round((u.empresas_ativas / maior) * 100))}%` }} />
        </span>
      </span>
    ),
  },
  { chave: "n", titulo: "Empresas ativas", numero: true, celula: (u) => MILHAR.format(u.empresas_ativas) },
  {
    chave: "ver",
    titulo: "Explorar",
    celula: (u) => (
      <VerAsEmpresas cnae={cnae} uf={u.uf} rotulo={`Ver as empresas do setor em ${u.uf}`} texto="Ver as empresas" />
    ),
  },
];
const COLUNAS_DE_ABERTURAS: Coluna<AberturasPorAnoV1>[] = [
  { chave: "ano", titulo: "Ano", celula: (a) => String(a.ano) },
  { chave: "n", titulo: "Aberturas", numero: true, celula: (a) => MILHAR.format(a.aberturas) },
];

function Barras({ itens }: { itens: AberturasPorAnoV1[] }) {
  const maior = Math.max(1, ...itens.map((i) => i.aberturas));
  return (
    <div className="barras-do-setor" role="img" aria-label="Aberturas por ano, em barras">
      {itens.map((i) => (
        <span
          key={i.ano}
          className="barra-do-setor"
          style={{ height: `${Math.max(2, Math.round((i.aberturas / maior) * 100))}%` }}
          title={`${i.ano}: ${MILHAR.format(i.aberturas)}`}
        />
      ))}
    </div>
  );
}

function Numeros({ dados, cnae, uf }: { dados: PerfilDoSetorV1; cnae: string; uf: string | null }) {
  if (dados.estado === "nao_liberada") {
    return <Vazio frase="Os números deste setor ainda não foram liberados nesta base. Isto não quer dizer que ele não tenha empresas." />;
  }
  const retrato = dados.data_do_retrato ? formatarMes(`${dados.data_do_retrato}-01`) : null;
  const fonte = <Fonte nome="Receita Federal (cadastro do CNPJ)" data={retrato} />;
  return (
    <section className="secao-do-relatorio" aria-labelledby="numeros-do-setor">
      <h2 id="numeros-do-setor">Números do setor (CNAE {dados.cnae_principal})</h2>
      <div className="numeros">
        <CartaoDeNumero
          rotulo="Empresas ativas"
          valor={dados.empresas_ativas === null ? null : MILHAR.format(dados.empresas_ativas)}
          detalhe="Com ao menos um estabelecimento ativo no CNAE"
          fonte={fonte}
          principal
        />
      </div>
      <p>
        <VerAsEmpresas
          cnae={cnae}
          uf={uf}
          rotulo={uf ? `Ver as empresas deste CNAE em ${uf}` : "Ver as empresas do setor"}
          texto={uf ? `Ver as empresas em ${uf}` : "Ver as empresas do setor"}
        />
      </p>
      <h3>Por UF</h3>
      {dados.por_uf === null ? (
        <p className="apagado">{NAO_CONSULTADO}</p>
      ) : (
        <>
          <Tabela
            legenda="Empresas ativas do setor por UF"
            colunas={colunasDaUf(cnae, Math.max(1, ...dados.por_uf.map((u) => u.empresas_ativas)))}
            linhas={dados.por_uf}
            chaveDaLinha={(u) => u.uf}
            vazio="Nenhuma empresa ativa neste CNAE."
            rodape={fonte}
          />
          <p className="apagado">A soma das UFs pode passar do total: a empresa conta em cada UF onde tem estabelecimento ativo.</p>
        </>
      )}
      <h3>Aberturas por ano</h3>
      {dados.aberturas_por_ano === null ? (
        <p className="apagado">{NAO_CONSULTADO}</p>
      ) : (
        <>
          <Barras itens={dados.aberturas_por_ano} />
          <p className="apagado">
            O último ano está incompleto: conta só até {dados.como_era_em ? formatarData(dados.como_era_em) : "o dia da consulta"}, e o
            retrato do cadastro vai até {retrato ?? "a data dele"}. Empresas já baixadas entram, e quem mudou de atividade conta no ano em que abriu.
          </p>
          <Tabela
            legenda="Aberturas de empresas do setor por ano"
            colunas={COLUNAS_DE_ABERTURAS}
            linhas={dados.aberturas_por_ano}
            chaveDaLinha={(a) => String(a.ano)}
            rodape={fonte}
          />
        </>
      )}
      <p className="apagado">Só pessoa jurídica: MEI e empresário individual não entram nestas contas.</p>
    </section>
  );
}

export function NumerosDoSetor({ cnae, uf }: { cnae: string; uf: string | null }) {
  const pedido = usarPedido<PerfilDoSetorV1>(ROTA, {}, { cnae });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Contando as empresas do setor…" />;
  if (pedido.estado === "erro") return <Erro erro={pedido.erro} />;
  return <Numeros dados={pedido.dados} cnae={cnae} uf={uf} />;
}
