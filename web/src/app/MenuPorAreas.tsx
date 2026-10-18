// O menu lateral do app novo por áreas (ADR 0096): o Início no topo, os favoritos da pessoa e uma seção
// por área (Ativo, Estratégias, Acompanhar) que recolhe. A tela que ainda não está no app novo aparece
// apagada, "em breve", sem link morto. Entre 761 e 1.100 px o menu vira um trilho de ícones e as telas
// de cada área abrem ao lado, ao passar o mouse ou com o Tab.
// Favoritos e áreas recolhidas ficam no localStorage do navegador (preferência de tela, sem dado pessoal);
// se o navegador recusar (navegação privada), valem só nesta visita.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { linkDoApp } from "../site/textos";
import { AREAS, AREAS_DO_MENU, type ItemDoMenu, areaDoEndereco, itensDaArea, primeiraPronta } from "./areas";
import { Icone } from "./Icone";

const FAVORITOS = "tickerlab.menu.favoritos";
const RECOLHIDAS = "tickerlab.menu.recolhidas";
const CONSULTA_DO_TRILHO = "(min-width: 761px) and (max-width: 1100px)";

/** Uma lista de chaves guardada no navegador; lixo ou navegador que recusa viram lista vazia. */
function lerLista(chave: string): string[] {
  try {
    const lido: unknown = JSON.parse(localStorage.getItem(chave) ?? "[]");
    return Array.isArray(lido) ? lido.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function gravarLista(chave: string, lista: string[]) {
  try {
    localStorage.setItem(chave, JSON.stringify(lista));
  } catch {
    // navegação privada que recusa: a escolha vale só até fechar a aba
  }
}

/** A lista de chaves com estado no React e cópia no navegador. */
function useListaGuardada(chave: string) {
  const [lista, setLista] = useState(() => lerLista(chave));
  // estável entre renderizações: o efeito que abre a área da tela aberta depende dela
  const mudar = useCallback(
    (nova: string[]) => {
      setLista(nova);
      gravarLista(chave, nova);
    },
    [chave],
  );
  return [lista, mudar] as const;
}

/** Verdadeiro entre 761 e 1.100 px (o jsdom dos testes não tem matchMedia: aí, falso). */
function useTrilho(): boolean {
  const [trilho, setTrilho] = useState(() => window.matchMedia?.(CONSULTA_DO_TRILHO).matches ?? false);
  useEffect(() => {
    const consulta = window.matchMedia?.(CONSULTA_DO_TRILHO);
    if (!consulta) return;
    const mudar = () => setTrilho(consulta.matches);
    consulta.addEventListener("change", mudar);
    return () => consulta.removeEventListener("change", mudar);
  }, []);
  return trilho;
}

// as telas que podem ser favoritas: as prontas das áreas do menu, pela chave
const PRONTAS = new Map(
  AREAS_DO_MENU.flatMap((area) => itensDaArea(area))
    .filter((item) => item.pronta)
    .map((item) => [item.pagina.chave, item] as const),
);

interface PropriedadesDoItem {
  item: ItemDoMenu;
  favorita: boolean;
  alternarFavorita(chave: string): void;
}

function ItemDaArea({ item, favorita, alternarFavorita }: PropriedadesDoItem) {
  const { pagina, pronta } = item;
  if (!pronta) {
    return (
      <li className="em-breve">
        <span>{pagina.titulo}</span> <span className="selo-em-breve">em breve</span>
      </li>
    );
  }
  return (
    <li>
      <NavLink to={`/${pagina.url}`}>{pagina.titulo}</NavLink>
      <button
        type="button"
        className="estrela"
        aria-pressed={favorita}
        aria-label={`Favoritar ${pagina.titulo}`}
        title={favorita ? "Tirar dos favoritos" : "Pôr nos favoritos"}
        onClick={() => alternarFavorita(pagina.chave)}
      >
        <Icone nome="estrela" />
      </button>
    </li>
  );
}

export function MenuPorAreas() {
  const atual = areaDoEndereco(useLocation().pathname);
  const trilho = useTrilho();
  const [favoritos, setFavoritos] = useListaGuardada(FAVORITOS);
  const [recolhidas, setRecolhidas] = useListaGuardada(RECOLHIDAS);

  // chegar numa tela de uma área recolhida abre a área (o link da tela aberta fica à vista); só na
  // chegada: depois disso a pessoa pode recolher a área da tela aberta também
  const areaDaChegada = useRef<string | null>(null);
  useEffect(() => {
    if (atual === areaDaChegada.current) return;
    areaDaChegada.current = atual;
    if (atual && recolhidas.includes(atual)) setRecolhidas(recolhidas.filter((a) => a !== atual));
  }, [atual, recolhidas, setRecolhidas]);

  const validos = favoritos.filter((chave) => PRONTAS.has(chave));
  const alternarFavorita = (chave: string) =>
    setFavoritos(validos.includes(chave) ? validos.filter((c) => c !== chave) : [...validos, chave]);
  const alternarArea = (area: string) =>
    setRecolhidas(recolhidas.includes(area) ? recolhidas.filter((a) => a !== area) : [...recolhidas, area]);

  return (
    <nav className={trilho ? "app-menu trilho" : "app-menu"} aria-label="Telas">
      <NavLink to="/" end className="inicio-do-menu" title="Início">
        <Icone nome="inicio" />
        <span className="rotulo-do-menu">Início</span>
      </NavLink>
      {validos.length > 0 ? (
        <section className="area-do-menu favoritos-do-menu" aria-labelledby="menu-favoritos">
          <h2 id="menu-favoritos" className="titulo-da-area" title="Favoritos">
            <Icone nome="estrela" />
            <span className="rotulo-do-menu">Favoritos</span>
          </h2>
          <ul className="itens-da-area">
            {validos.map((chave) => (
              <ItemDaArea key={chave} item={PRONTAS.get(chave)!} favorita alternarFavorita={alternarFavorita} />
            ))}
          </ul>
        </section>
      ) : null}
      {AREAS.filter((a) => AREAS_DO_MENU.includes(a.chave)).map((area) => {
        const aberta = !recolhidas.includes(area.chave);
        const lista = `menu-${area.chave}`;
        return (
          <section key={area.chave} className={atual === area.chave ? "area-do-menu atual" : "area-do-menu"}>
            <h2 className="titulo-da-area">
              <button
                type="button"
                title={area.rotulo}
                aria-expanded={trilho ? undefined : aberta}
                aria-controls={trilho ? undefined : lista}
                onClick={() => alternarArea(area.chave)}
              >
                <Icone nome={area.icone} />
                <span className="rotulo-do-menu">{area.rotulo}</span>
              </button>
            </h2>
            {/* no trilho a lista abre ao lado pelo CSS (:hover e :focus-within), recolhida ou não */}
            <ul id={lista} className="itens-da-area" hidden={!trilho && !aberta}>
              {itensDaArea(area.chave).map((item) => (
                <ItemDaArea
                  key={item.pagina.chave}
                  item={item}
                  favorita={validos.includes(item.pagina.chave)}
                  alternarFavorita={alternarFavorita}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </nav>
  );
}

// --- celular (até 760 px, só CSS): 5 abas embaixo, ao alcance do polegar (ADR 0066 e 0096) ---

// na folha "Mais": as telas prontas de cada área e as da Conta
const AREAS_DA_FOLHA = AREAS.filter((a) => [...AREAS_DO_MENU, "conta"].includes(a.chave)).map((area) => ({
  area,
  telas: itensDaArea(area.chave).filter((item) => item.pronta),
}));

/** Início, uma aba por área (abre a primeira tela pronta dela) e "Mais", que abre a folha com todas. */
export function AbasDoCelular() {
  const { pathname } = useLocation();
  const atual = areaDoEndereco(pathname);
  const folha = useRef<HTMLDialogElement>(null);
  const [aberta, setAberta] = useState(false);
  // o jsdom dos testes (e navegador antigo) não tem showModal: aí a folha abre sem o fundo escuro
  const abrir = () => {
    const dialogo = folha.current;
    if (!dialogo) return;
    if (typeof dialogo.showModal === "function") dialogo.showModal();
    else dialogo.open = true;
    setAberta(true);
  };
  const fechar = () => {
    const dialogo = folha.current;
    if (!dialogo) return;
    if (typeof dialogo.close === "function") dialogo.close();
    else dialogo.open = false;
    setAberta(false);
  };
  return (
    <>
      <nav className="app-abas" aria-label="Telas, atalhos">
        <NavLink to="/" end>
          <Icone nome="inicio" />
          <span>Início</span>
        </NavLink>
        {AREAS.filter((a) => AREAS_DO_MENU.includes(a.chave)).map((area) => {
          const destino = primeiraPronta(area.chave);
          if (!destino) return null;
          const marcada = atual === area.chave;
          const endereco = `/${destino.url}`;
          return (
            <Link
              key={area.chave}
              to={endereco}
              className={marcada ? "active" : undefined}
              // "page" só na própria tela; nas outras telas da área, a aba é a atual do conjunto
              aria-current={marcada ? (pathname.replace(/\/+$/, "") === endereco ? "page" : "true") : undefined}
            >
              <Icone nome={area.icone} />
              <span>{area.rotulo}</span>
            </Link>
          );
        })}
        <button
          type="button"
          className={atual === "conta" ? "active" : undefined}
          aria-haspopup="dialog"
          aria-expanded={aberta}
          onClick={abrir}
        >
          <Icone nome="mais" />
          <span>Mais</span>
        </button>
      </nav>
      {/* fora da barra: ela é fixa e borrada (backdrop-filter), e prenderia a folha dentro dela */}
      <dialog
        ref={folha}
        className="folha-mais"
        aria-labelledby="titulo-da-folha"
        onClose={() => setAberta(false)}
        // o fundo escuro em volta da folha é o próprio dialog: tocar nele fecha
        onClick={(evento) => {
          if (evento.target === evento.currentTarget) fechar();
        }}
      >
        <div className="cabeca-da-folha">
          <h2 id="titulo-da-folha">Todas as telas</h2>
          <button type="button" className="botao pequeno" onClick={fechar}>
            Fechar
          </button>
        </div>
        {AREAS_DA_FOLHA.map(({ area, telas }) => (
          <section key={area.chave}>
            <h3>{area.rotulo}</h3>
            {telas.map(({ pagina }) => (
              <NavLink key={pagina.chave} to={`/${pagina.url}`} onClick={fechar}>
                {pagina.titulo}
              </NavLink>
            ))}
          </section>
        ))}
        {/* no celular o "App atual" não cabe no topo: fica aqui */}
        <a className="app-atual-na-folha" href={linkDoApp()}>
          App atual
        </a>
      </dialog>
    </>
  );
}
