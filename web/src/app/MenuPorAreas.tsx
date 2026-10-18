// O menu lateral do app novo por áreas (ADR 0096): o Início no topo, os favoritos da pessoa e uma seção
// por área (Ativo, Estratégias, Acompanhar) que recolhe. A tela que ainda não está no app novo aparece
// apagada, "em breve", sem link morto. Entre 761 e 1.100 px o menu vira um trilho de ícones e as telas
// de cada área abrem ao lado, ao passar o mouse ou com o Tab.
// Favoritos e áreas recolhidas ficam no localStorage do navegador (preferência de tela, sem dado pessoal);
// se o navegador recusar (navegação privada), valem só nesta visita.
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router";
import { AREAS, AREAS_DO_MENU, type ItemDoMenu, areaDoEndereco, itensDaArea } from "./areas";
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
  const mudar = (nova: string[]) => {
    setLista(nova);
    gravarLista(chave, nova);
  };
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

  // abrir uma tela de uma área recolhida abre a área (o link da tela aberta fica à vista)
  useEffect(() => {
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
