// As telas do app novo: as páginas que já têm contrato na API (src/paginas.py), no mesmo endereço de
// sempre (app.tickerlab.com.br/visao-geral). Página que ainda só existe na versão clássica (o Streamlit
// em /classico) leva à mesma página lá: o link antigo continua funcionando (plano de 18/10).
import { type ReactNode, useEffect } from "react";
import { Navigate, useLocation } from "react-router";
import { type PaginaDoApp, paginasDoApp } from "../conteudo";
import { linkDoClassico } from "./classico";
import { navegador } from "./navegador";
import { Backtest } from "./telas/Backtest";
import { BuscaPorCnpj } from "./telas/BuscaPorCnpj";
import { Comparar } from "./telas/Comparar";
import { EmConstrucao } from "./telas/EmConstrucao";
import { JurosEInflacao } from "./telas/JurosEInflacao";
import { LinhaDoTempo } from "./telas/LinhaDoTempo";
import { MapaDoCafe } from "./telas/MapaDoCafe";
import { MeusDados } from "./telas/MeusDados";
import { PainelDoCafe } from "./telas/PainelDoCafe";
import { Planos } from "./telas/Planos";
import { PrecosDeReferencia } from "./telas/PrecosDeReferencia";
import { RelatorioDoSetor } from "./telas/RelatorioDoSetor";
import { RelatorioEmpresa } from "./telas/RelatorioEmpresa";
import { Sala } from "./telas/Sala";
import { RetornoMensal } from "./telas/RetornoMensal";
import { Risco } from "./telas/Risco";
import { Simulacoes } from "./telas/Simulacoes";
import { VisaoGeral } from "./telas/VisaoGeral";

export const TELAS_DO_APP: PaginaDoApp[] = paginasDoApp.filter((p) => p.contrato !== null);

// as telas já feitas em React, pela chave da página
const TELAS_PRONTAS: Record<string, (pagina: PaginaDoApp) => ReactNode> = {
  visao_geral: (pagina) => <VisaoGeral pagina={pagina} />,
  juros_e_inflacao: (pagina) => <JurosEInflacao pagina={pagina} />,
  precos_de_referencia: (pagina) => <PrecosDeReferencia pagina={pagina} />,
  linha_do_tempo: (pagina) => <LinhaDoTempo pagina={pagina} />,
  risco: (pagina) => <Risco pagina={pagina} />,
  retorno_mensal: (pagina) => <RetornoMensal pagina={pagina} />,
  comparar: (pagina) => <Comparar pagina={pagina} />,
  backtest: (pagina) => <Backtest pagina={pagina} />,
  planos: (pagina) => <Planos pagina={pagina} />,
  relatorio_empresa: (pagina) => <RelatorioEmpresa pagina={pagina} />,
  busca_por_cnpj: (pagina) => <BuscaPorCnpj pagina={pagina} />,
  relatorio_do_setor: (pagina) => <RelatorioDoSetor pagina={pagina} />,
  meus_dados: (pagina) => <MeusDados pagina={pagina} />,
  simulacoes: (pagina) => <Simulacoes pagina={pagina} />,
  sala_de_dados: () => <Sala />,
  mapa_do_cafe: (pagina) => <MapaDoCafe pagina={pagina} />,
  painel_do_cafe: (pagina) => <PainelDoCafe pagina={pagina} />,
  // o Pulse é o Workspace: o Início do app novo
  pulse: () => <Navigate to="/" replace />,
};

/** A página já tem tela em React? (Sem tela, leva à mesma página na versão clássica.) */
export const temTelaPronta = (chave: string) => chave in TELAS_PRONTAS;

// a página inicial da versão clássica (url "inicio", servida na raiz do Streamlit) é o Início do app novo
const URL_DA_INICIAL_DO_CLASSICO = "inicio";
// a área de administração fica fora do bundle de propósito (scripts/exportar_conteudo.py): só o
// endereço entra aqui, para o link antigo chegar lá; quem autoriza continua sendo o servidor
const ENDERECO_DA_ADMINISTRACAO = "admin";

/** Os endereços das páginas que ainda só existem na versão clássica (sem contrato na API). */
export const ENDERECOS_SO_DO_CLASSICO: string[] = [
  ...paginasDoApp
    .filter((p) => p.contrato === null && p.url !== URL_DA_INICIAL_DO_CLASSICO)
    .map((p) => p.url),
  ENDERECO_DA_ADMINISTRACAO,
];

/** O endereço (sem as barras) se o caminho é de uma página só da versão clássica; senão, null. */
export function enderecoSoDoClassico(pathname: string): string | null {
  const endereco = pathname.replace(/^\/+|\/+$/g, "");
  return ENDERECOS_SO_DO_CLASSICO.includes(endereco) ? endereco : null;
}

/** A página inicial da versão clássica, pelo endereço antigo, é o Início do app novo. */
export const eAInicialDoClassico = (pathname: string) =>
  pathname.replace(/^\/+|\/+$/g, "") === URL_DA_INICIAL_DO_CLASSICO;

/** Leva à mesma página na versão clássica, com os mesmos parâmetros; o link fica à vista caso a
 * ida automática falhe. Fora do login do app novo: quem tem o link antigo não precisa entrar aqui. */
export function ParaOClassico({ endereco }: { endereco: string }) {
  const { search } = useLocation();
  const destino = linkDoClassico(endereco) + search;
  useEffect(() => {
    navegador.trocar(destino);
  }, [destino]);
  return (
    <section className="aviso-do-app">
      <p>Esta página está na versão clássica do app. Abrindo…</p>
      <a className="botao primario" href={destino}>
        Abrir na versão clássica
      </a>
    </section>
  );
}

export function telaDa(pagina: PaginaDoApp): ReactNode {
  const tela = TELAS_PRONTAS[pagina.chave];
  return tela ? tela(pagina) : <EmConstrucao pagina={pagina} />;
}
