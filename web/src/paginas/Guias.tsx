// Guias de busca: uma página para cada pergunta que quem analisa empresas digita ("quem audita uma
// companhia aberta", "troca de auditor", "sócios e grupo econômico de um CNPJ"...). Linha 336 da fila,
// a partir de projeto-acoes/busca-organica.md. Cada guia diz o que a base responde, de que tabela vem
// (a frase, o órgão e o desde vêm do catálogo, nunca digitados aqui), como chegar no app e o que a
// base NÃO responde. Sem número de mercado, sem preço, sem opinião: só o caminho até a fonte.
import { catalogo } from "../conteudo";
import type { TabelaDaBase } from "../conteudo";
import { PaginaDeLeitura, ancora } from "../site/Leitura";
import { linkDoApp } from "../site/textos";

interface Guia {
  arquivo: string;
  titulo: string;
  descricao: string;
  resposta: string; // a resposta curta, no topo
  tabelas: string[]; // nomes no catálogo
  passos: string[];
  naoResponde: string[];
  veja: [string, string][]; // [texto, endereço]
}

const ATALHO_EMPRESA = linkDoApp("relatorio-empresa");
const ATALHO_CNPJ = linkDoApp("busca-por-cnpj");
const ATALHO_SETOR = linkDoApp("relatorio-do-setor");

export const GUIAS: Guia[] = [
  {
    arquivo: "quem-audita-uma-companhia-aberta.html",
    titulo: "Quem audita uma companhia aberta",
    descricao:
      "Onde achar o auditor de uma companhia aberta, desde quando ele atua e o tipo de parecer que assinou, com a fonte (CVM) de cada dado.",
    resposta:
      "O auditor de cada companhia aberta vem do Formulário Cadastral (FCA) entregue à CVM, com a firma, o início e o fim de cada mandato. O parecer de cada demonstração anual (DFP) e trimestral (ITR) vem dos arquivos de pareceres da CVM.",
    tabelas: ["auditores", "pareceres_dfp", "pareceres_itr"],
    passos: [
      "Abra o Relatório da empresa no app e digite o ticker da companhia (por exemplo, PETR4).",
      "Na seção “Auditor e controladas”, veja a firma atual, desde quando ela audita e a tabela de trocas de auditor, cada uma com a data e a fonte.",
      "Para ver como isso fica num relatório pronto, abra o relatório de exemplo.",
    ],
    naoResponde: [
      "Não avalia a qualidade do trabalho do auditor: mostra quem assinou e o tipo de opinião, como a CVM registra.",
      "Só companhias abertas têm esse cadastro na CVM; empresa fechada não aparece aqui.",
      "Auditor que é pessoa física não tem o nome mostrado.",
    ],
    veja: [
      ["Abrir o Relatório da empresa no app", ATALHO_EMPRESA],
      ["Relatório de exemplo de uma companhia", "/relatorio-de-exemplo.html"],
      ["Relatório do setor elétrico, com o auditor atual de cada companhia", "/relatorio-de-setor-eletricas.html"],
      ["Troca de auditor das companhias abertas", "/troca-de-auditor-companhias-abertas.html"],
    ],
  },
  {
    arquivo: "troca-de-auditor-companhias-abertas.html",
    titulo: "Troca de auditor das companhias abertas",
    descricao:
      "Como ver quando uma companhia aberta trocou de firma de auditoria: cada troca sai dos mandatos que a CVM publica e não é reescrita depois.",
    resposta:
      "A base monta um rótulo “trocou de auditor” a partir de todos os anos de auditores, na ordem em que os cadastros (FCA) foram entregues. Cada troca mostra a firma anterior, a nova, a data e quantos anos durou o mandato anterior, e uma troca registrada não é reescrita depois.",
    tabelas: ["trocas_de_auditor", "auditores"],
    passos: [
      "Abra o Relatório da empresa no app e digite o ticker da companhia.",
      "Em “Auditor e controladas”, veja a tabela “Trocas de auditor”: a firma anterior, a nova, a data e os anos com a anterior.",
      "Para acompanhar um setor, abra o relatório semanal do setor elétrico, que traz o auditor atual de cada companhia lado a lado.",
    ],
    naoResponde: [
      "A CVM tem regra de rodízio de auditores; o TickerLab mostra as datas dos mandatos, mas não afirma se a regra foi cumprida em cada caso.",
      "A troca é lida do cadastro entregue, então aparece quando o cadastro novo é entregue, não no dia em que a empresa decidiu.",
      "Não explica o motivo da troca: o motivo, quando existe, está nos documentos da companhia.",
    ],
    veja: [
      ["Quem audita uma companhia aberta", "/quem-audita-uma-companhia-aberta.html"],
      ["Relatório do setor elétrico, com o auditor atual de cada companhia", "/relatorio-de-setor-eletricas.html"],
      ["De onde vêm os dados", "/metodologia.html"],
    ],
  },
  {
    arquivo: "socios-e-grupo-economico-por-cnpj.html",
    titulo: "Sócios e grupo econômico de um CNPJ",
    descricao:
      "A partir de um CNPJ: as controladas e coligadas que a companhia informa, os acionistas do Formulário de Referência e as empresas ligadas, com data e fonte.",
    resposta:
      "Para companhia aberta, o grupo vem das controladas e coligadas que ela informa à CVM no Formulário de Referência. Para as demais empresas, vem das ligações que a base registra. Cada linha mostra a fonte e a data.",
    tabelas: ["cnpj_qsa", "controladas", "ligacoes", "fre_acionistas"],
    passos: [
      "Abra a Busca por CNPJ no app e digite o CNPJ da empresa, com ou sem pontuação.",
      "Veja quem é a empresa, o grupo e a rede de empresas ligadas, cada relação com a data e a fonte.",
      "Para uma companhia aberta, o relatório completo mostra também as controladas e coligadas por ano.",
    ],
    naoResponde: [
      "O quadro de sócios da Receita ainda não está na base: o grupo das empresas fechadas vem só das ligações registradas.",
      "Sócio pessoa física não é detalhado: o TickerLab não mostra CPF, contato nem endereço residencial.",
      "Ligação por sobrenome ou por nome parecido não vira relação: só entram vínculos que a fonte registra.",
      "Participação indireta e controle de fato podem não aparecer se não estiverem nos documentos entregues.",
    ],
    veja: [
      ["Abrir a Busca por CNPJ no app", ATALHO_CNPJ],
      ["Relatório de exemplo, com as controladas de uma companhia", "/relatorio-de-exemplo.html"],
      ["Tabelas e licenças de cada fonte", "/dados.html"],
      ["De onde vêm os dados", "/metodologia.html"],
    ],
  },
  {
    arquivo: "fusoes-e-aquisicoes-das-companhias-abertas.html",
    titulo: "Fusões e aquisições das companhias abertas",
    descricao:
      "Os documentos que companhias abertas entregam à CVM e que podem anunciar fusão, aquisição ou venda, com a data de entrega e o link do original.",
    resposta:
      "A base guarda os documentos que as companhias abertas entregam à CVM no sistema IPE e que podem anunciar uma operação de M&A, como fatos relevantes e comunicados, uma linha por versão entregue.",
    tabelas: ["ma_candidatos"],
    passos: [
      "Abra o Relatório da empresa no app e digite o ticker; a seção “Negócios e eventos” reúne os documentos da companhia.",
      "Para um setor, abra o Relatório do setor e veja as companhias lado a lado.",
      "Cada item leva ao documento original na CVM.",
    ],
    naoResponde: [
      "São candidatos a M&A: o documento pode anunciar uma operação, mas a base não confirma que ela foi concluída nem avalia o valor.",
      "Só companhias abertas entregam esses documentos; negócio entre empresas fechadas não aparece.",
      "Sem valores e sem a outra parte do negócio; esta página não traz ranking de setores nem de assessores financeiros.",
    ],
    veja: [
      ["Abrir o Relatório da empresa no app", ATALHO_EMPRESA],
      ["Abrir o Relatório do setor no app", ATALHO_SETOR],
      ["Relatório de exemplo, seção “Negócios e eventos”", "/relatorio-de-exemplo.html"],
      ["Ofertas públicas de uma empresa", "/ofertas-publicas-de-acoes-e-debentures.html"],
    ],
  },
  {
    arquivo: "ofertas-publicas-de-acoes-e-debentures.html",
    titulo: "Ofertas públicas de ações e debêntures de uma empresa",
    descricao:
      "As ofertas públicas registradas na CVM por emissor, antes e depois da Resolução CVM 160, com a fonte e a data de cada linha.",
    resposta:
      "As ofertas públicas registradas na CVM entram na base por CNPJ do emissor, no formato da CVM: as anteriores à Resolução 160 (a partir de 1989) e os requerimentos pela Resolução 160 (de 2023 em diante).",
    tabelas: ["ofertas_antigas", "ofertas_resolucao_160"],
    passos: [
      "Abra o Relatório da empresa no app e digite o ticker; a seção “Ofertas e fundos” mostra as ofertas do emissor.",
      "Ou digite o CNPJ na Busca por CNPJ para ver o emissor e as ofertas ligadas a ele.",
      "Para ver o formato num relatório pronto, abra o relatório de exemplo.",
    ],
    naoResponde: [
      "Mostra o que foi registrado na CVM, não o resultado da oferta nem a demanda por ela.",
      "Os textos livres dos requerimentos (devedores, garantias e outros) não entram na base.",
      "Oferta que não passa pela CVM, como a de empresa que não registra oferta, não aparece.",
    ],
    veja: [
      ["Abrir o Relatório da empresa no app", ATALHO_EMPRESA],
      ["Abrir a Busca por CNPJ no app", ATALHO_CNPJ],
      ["Relatório de exemplo, seção “Ofertas e fundos”", "/relatorio-de-exemplo.html"],
      ["Fusões e aquisições das companhias abertas", "/fusoes-e-aquisicoes-das-companhias-abertas.html"],
    ],
  },
];

const TITULO_RESPOSTA = "A resposta curta";
const TITULO_TABELAS = "De onde vem na base";
const TITULO_PASSOS = "Como consultar";
const TITULO_LIMITES = "O que esta página não responde";
const TITULO_VEJA = "Veja também";

const SUMARIO = [TITULO_RESPOSTA, TITULO_TABELAS, TITULO_PASSOS, TITULO_LIMITES, TITULO_VEJA].map(
  (texto) => ({ id: ancora(texto), texto }),
);

export function dadosDoGuia(guia: Guia) {
  return {
    caminho: `/${guia.arquivo}`,
    titulo: guia.titulo,
    descricao: guia.descricao,
    atual: "/relatorios.html",
  };
}

// O catálogo público só tem tabela montada (linha 916): a que ainda não tem arquivo some do guia, em vez
// de prometer um dado que a base não entrega. O guia nunca fica sem nenhuma (conferido no build).
function tabelasDoCatalogo(nomes: string[]): TabelaDaBase[] {
  const achadas = nomes
    .map((nome) => catalogo.tabelas.find((t) => t.tabela === nome))
    .filter((t): t is TabelaDaBase => t !== undefined);
  if (achadas.length === 0) throw new Error(`Guia sem nenhuma tabela montada: ${nomes.join(", ")}`);
  return achadas;
}

// o catálogo traz 2010 (padrão da CVM) para as ofertas, que começam em 1989 e 2023: a data real está na frase
const SEM_DESDE = new Set(["ofertas_antigas", "ofertas_resolucao_160"]);

function desde(iso: string): string {
  return iso.slice(0, 4);
}

export function GuiaDeBusca({ guia }: { guia: Guia }) {
  return (
    <PaginaDeLeitura
      olho="Guia de busca"
      titulo={guia.titulo}
      subtitulo="Onde está a resposta na base do TickerLab, com a fonte e o que ela não diz."
      sumario={SUMARIO}
    >
      <p className="v2-aviso">
        Este guia aponta onde achar o dado. Nada aqui é recomendação de investimento.
      </p>

      <h2 id={ancora(TITULO_RESPOSTA)}>{TITULO_RESPOSTA}</h2>
      <p>{guia.resposta}</p>

      <h2 id={ancora(TITULO_TABELAS)}>{TITULO_TABELAS}</h2>
      <ul>
        {tabelasDoCatalogo(guia.tabelas).map((t) => {
          return (
            <li key={t.tabela}>
              {t.frase}{" "}
              <small>
                Fonte: {t.orgao}; atualização: {t.frequencia.toLowerCase()}
                {SEM_DESDE.has(t.tabela) ? "." : `; histórico desde ${desde(t.historico_desde)}.`}
              </small>
            </li>
          );
        })}
      </ul>

      <h2 id={ancora(TITULO_PASSOS)}>{TITULO_PASSOS}</h2>
      <ol>
        {guia.passos.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ol>

      <h2 id={ancora(TITULO_LIMITES)}>{TITULO_LIMITES}</h2>
      <ul>
        {guia.naoResponde.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>

      <h2 id={ancora(TITULO_VEJA)}>{TITULO_VEJA}</h2>
      <ul>
        {guia.veja.map(([texto, href]) => (
          <li key={href}>
            <a href={href}>{texto}</a>
          </li>
        ))}
      </ul>
    </PaginaDeLeitura>
  );
}
