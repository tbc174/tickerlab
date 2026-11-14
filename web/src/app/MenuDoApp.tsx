// O menu do app (linha 903): os mesmos sete itens em toda tela, na ordem de src/paginas.py. Ao lado no
// computador; entre 761 e 1.100 px, só os ícones (o nome fica no "title" e para o leitor de tela); no celular
// (até 760 px), abas fixas embaixo, ao alcance do polegar (ADR 0066). As telas que não têm item no menu
// continuam abrindo pelo endereço e pela lista "Todas as telas", que também leva à versão clássica.
import { Link, NavLink, useLocation } from "react-router";
import { AREAS, telasProntasDaArea } from "./areas";
import { linkDoClassico } from "./classico";
import type { Dialogo } from "./dialogo";
import { Icone } from "./Icone";
import { ITENS_COM_ABA, ITENS_DO_MENU, type ItemDoMenu, itemDoEndereco, marcaDoItem } from "./menu";
import { Selo } from "./pecas/Selo";

const TODAS_AS_TELAS = "Todas as telas";

function LinkDoItem({ item }: { item: ItemDoMenu }) {
  const marca = marcaDoItem(item, useLocation().pathname);
  return (
    <Link to={item.destino} className={marca ? "active" : undefined} aria-current={marca} title={item.rotulo}>
      <Icone nome={item.icone} />
      <span className="rotulo-do-menu">{item.rotulo}</span>
      {item.novo ? <Selo tom="destaque">Novo</Selo> : null}
    </Link>
  );
}

function ListaDeItens({ itens }: { itens: ItemDoMenu[] }) {
  return (
    <ul className="itens-do-menu">
      {itens.map((item) => (
        <li key={item.chave}>
          <LinkDoItem item={item} />
        </li>
      ))}
    </ul>
  );
}

export function MenuDoApp({ todasAsTelas }: { todasAsTelas: Dialogo }) {
  const principais = ITENS_DO_MENU.filter((item) => !item.secundario);
  const secundarios = ITENS_DO_MENU.filter((item) => item.secundario);
  return (
    <nav className="app-menu" aria-label="Telas">
      <ListaDeItens itens={principais} />
      {secundarios.length > 0 ? <ListaDeItens itens={secundarios} /> : null}
      <button
        type="button"
        className="todas-do-menu"
        title={TODAS_AS_TELAS}
        aria-haspopup="dialog"
        aria-expanded={todasAsTelas.aberto}
        onClick={todasAsTelas.abrir}
      >
        <Icone nome="telas" />
        <span className="rotulo-do-menu">{TODAS_AS_TELAS}</span>
      </button>
    </nav>
  );
}

/** No celular: os primeiros itens do menu e "Mais", que abre a lista com todas as telas. */
export function AbasDoCelular({ todasAsTelas }: { todasAsTelas: Dialogo }) {
  const { pathname } = useLocation();
  const item = itemDoEndereco(pathname);
  // a tela aberta não tem aba (item secundário, tela da conta, tela fora do menu): quem fica marcado é o "Mais"
  const foraDasAbas = !ITENS_COM_ABA.some((daAba) => daAba.chave === item);
  return (
    <nav className="app-abas" aria-label="Telas, atalhos">
      {ITENS_COM_ABA.map((daAba) => {
        const marca = marcaDoItem(daAba, pathname);
        return (
          <Link key={daAba.chave} to={daAba.destino} className={marca ? "active" : undefined} aria-current={marca}>
            <Icone nome={daAba.icone} />
            <span>{daAba.rotulo}</span>
          </Link>
        );
      })}
      <button
        type="button"
        className={foraDasAbas ? "active" : undefined}
        aria-haspopup="dialog"
        aria-expanded={todasAsTelas.aberto}
        onClick={todasAsTelas.abrir}
      >
        <Icone nome="mais" />
        <span>Mais</span>
      </button>
    </nav>
  );
}

// toda tela que abre, pela área dela (o Início já é o primeiro item do menu)
const AREAS_COM_TELAS = AREAS.map((area) => ({ area, telas: telasProntasDaArea(area.chave) })).filter(
  ({ area, telas }) => area.chave !== "inicio" && telas.length > 0,
);

/** A lista de todas as telas que abrem, por área, e o caminho para a versão clássica. No celular sobe de
 * baixo, como uma folha; no computador abre no meio da tela. */
export function TodasAsTelas({ dialogo }: { dialogo: Dialogo }) {
  return (
    // fora da barra de abas: ela é fixa e borrada (backdrop-filter), e prenderia a folha dentro dela
    <dialog
      ref={dialogo.ref}
      className="folha-mais"
      aria-labelledby="titulo-da-folha"
      onClose={dialogo.aoFechar}
      onClick={dialogo.aoClicarNoFundo}
    >
      <div className="cabeca-da-folha">
        <h2 id="titulo-da-folha">{TODAS_AS_TELAS}</h2>
        <button type="button" className="botao pequeno" onClick={dialogo.fechar}>
          Fechar
        </button>
      </div>
      <div className="areas-da-folha">
        {AREAS_COM_TELAS.map(({ area, telas }) => (
          <section key={area.chave}>
            <h3>{area.rotulo}</h3>
            {telas.map((pagina) => (
              <NavLink key={pagina.chave} to={`/${pagina.url}`} onClick={dialogo.fechar}>
                {pagina.titulo}
              </NavLink>
            ))}
          </section>
        ))}
      </div>
      {/* o que ainda só existe na versão clássica: um link só, no lugar de uma linha apagada por tela */}
      <a className="app-atual-na-folha" href={linkDoClassico()}>
        Versão clássica
      </a>
    </dialog>
  );
}
