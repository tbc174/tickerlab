// A moldura de toda página do site: <head>, topo com o menu do tema, rodapé.
// Era a função `pagina()` de scripts/gerar_site.py; o HTML sai com a mesma estrutura.
import { join } from "node:path";
import type { ReactNode } from "react";
import { SOL_JS, lerTexto, versao } from "../arquivos";
import { marca } from "../conteudo";
import { css } from "../estilo";
import { Bruto } from "./Bruto";
import {
  ASSINATURA,
  AVISO,
  EMAIL_DE_CONTATO,
  URL_DO_CODIGO,
  URL_DO_SITE,
  linkDoApp,
} from "./textos";
import { OPCOES_DO_TEMA, TEMA_SALVO } from "./tema";

export { SOL_JS, versao };
export const SITE_JS = lerTexto(join(process.cwd(), "publico", "site.js"));

const ICONES_E_FONTE =
  '<link rel="icon" href="/marca/simbolo.svg" type="image/svg+xml">' +
  '<link rel="icon" href="/marca/icone.png" type="image/png">' +
  '<link rel="preload" href="/fontes/Manrope-VariableFont_wght.ttf" as="font" type="font/ttf" crossorigin>';

function Icone({ classe, desenho }: { classe: string; desenho: string }) {
  return (
    <svg className={classe} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d={desenho} />
    </svg>
  );
}

/** O botão do topo abre as três opções (o site.js cuida do teclado e de marcar a escolhida). */
function MenuDoTema() {
  return (
    <div className="tema-menu">
      <button
        className="tema"
        type="button"
        data-tema-botao=""
        aria-haspopup="menu"
        aria-expanded="false"
        aria-controls="opcoes-do-tema"
        aria-label="Tema: Automático"
      >
        {OPCOES_DO_TEMA.map(([valor, , desenho]) => (
          <Icone key={valor} classe={valor} desenho={desenho} />
        ))}
      </button>
      <div className="tema-opcoes" id="opcoes-do-tema" role="menu" aria-label="Tema" hidden>
        {OPCOES_DO_TEMA.map(([valor, nome, desenho, dica]) => (
          <button
            key={valor}
            type="button"
            role="menuitemradio"
            aria-checked="false"
            data-tema-escolha={valor}
          >
            <Icone classe="" desenho={desenho} />
            <span>
              {nome}
              {dica ? <small>{dica}</small> : null}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// o topo do símbolo segue o tema (marinho no claro, claro no escuro); a haste é sempre elétrica
function Logo() {
  return (
    <a className="marca" href="/" aria-label="TickerLab, página inicial">
      <Bruto html={marca.simbolo_svg} />
      <span>
        Ticker<b>Lab</b>
      </span>
    </a>
  );
}

const ITENS_DO_TOPO: [string, string][] = [
  ["/produto.html", "Produto"],
  ["/como-funciona.html", "Como funciona"],
  ["/#relatorios", "Relatórios"],
  ["/precos.html", "Planos"],
  ["/aprender.html", "Aprender"],
  ["/sobre.html", "Sobre"],
];

function Topo({ atual }: { atual: string }) {
  return (
    <header className="topo">
      <div className="faixa">
        <Logo />
        <nav aria-label="Principal">
          {ITENS_DO_TOPO.map(([href, nome]) => (
            <a key={href} href={href} aria-current={href === atual ? "page" : undefined}>
              {nome}
            </a>
          ))}
        </nav>
        <MenuDoTema />
        <a className="botao primario pequeno" href={linkDoApp()}>
          Abrir o app
        </a>
      </div>
    </header>
  );
}

function Rodape() {
  return (
    <footer className="rodape escura">
      <div className="faixa">
        <div>
          <Logo />
          <p className="apagado">{ASSINATURA}</p>
        </div>
        <nav aria-label="Rodapé">
          <a href="/sobre.html">Sobre</a>
          <a href="/metodologia.html">Fontes e metodologia</a>
          <a href="/precos.html">Planos</a>
          <a href="/termos.html">Termos de uso</a>
          <a href="/privacidade.html">Privacidade</a>
          <a href={URL_DO_CODIGO} rel="noopener">
            Código no GitHub
          </a>
          <a href={`mailto:${EMAIL_DE_CONTATO}`}>{EMAIL_DE_CONTATO}</a>
        </nav>
        <p className="aviso">{AVISO}</p>
      </div>
    </footer>
  );
}

export interface DadosDaPagina {
  caminho: string; // "/", "/produto.html"...
  titulo: string;
  descricao: string;
  atual?: string; // o item do topo marcado como página atual
}

export function Documento({
  caminho,
  titulo,
  descricao,
  atual = "",
  children,
}: DadosDaPagina & { children: ReactNode }) {
  const tituloCompleto = caminho === "/" ? "TickerLab" : `${titulo} · TickerLab`;
  const endereco = `${URL_DO_SITE}${caminho}`;
  return (
    <html lang="pt-BR">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{tituloCompleto}</title>
        <meta name="description" content={descricao} />
        <link rel="canonical" href={endereco} />
        <meta property="og:title" content={tituloCompleto} />
        <meta property="og:description" content={descricao} />
        <meta property="og:type" content="website" />
        <meta property="og:url" content={endereco} />
        <meta property="og:image" content={`${URL_DO_SITE}/marca/compartilhamento.png`} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content={`TickerLab: ${ASSINATURA}`} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="theme-color" content={marca.claro} />
        <script src={`/tema/sol.js?v=${versao(SOL_JS)}`} />
        <Bruto html={TEMA_SALVO} />
        {/* HTML pronto: com <link> do React, o React 19 sobe estes para antes dos scripts do tema */}
        <Bruto html={ICONES_E_FONTE} />
        <link rel="stylesheet" href={`/estilo.css?v=${versao(css())}`} />
        <script src={`/site.js?v=${versao(SITE_JS)}`} defer />
      </head>
      <body>
        <a className="pular" href="#conteudo">
          Pular para o conteúdo
        </a>
        <Topo atual={atual} />
        <main id="conteudo">{children}</main>
        <Rodape />
      </body>
    </html>
  );
}
