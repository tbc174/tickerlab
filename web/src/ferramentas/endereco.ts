// A simulação guardada no endereço (?capital=10.000&taxa=10...), para a pessoa mandar o link a
// alguém ou voltar a ela depois. Só as chaves do exemplo da ferramenta entram; onde o exemplo é
// número, só número; onde é escolha, só uma opção da lista. O resto cai no exemplo. Nada vai ao
// servidor: o endereço só muda no navegador (replaceState, sem encher o "voltar"). O HTML pronto do
// build sai sempre com o exemplo; o endereço é lido depois de ligar a ferramenta.
import { useCallback, useEffect, useRef, useState } from "react";
import { lerNumero } from "./numeros";

type Campos = Record<string, string>;
export type Opcoes<T extends Campos> = { readonly [K in keyof T]?: readonly string[] };

const TAMANHO_MAXIMO = 20; // "10.000.000,00" cabe com folga

function aceita(valor: string, exemplo: string, opcoes?: readonly string[]): boolean {
  if (opcoes) return opcoes.includes(valor);
  if (lerNumero(exemplo) === null) return false; // escolha sem lista de opções: não lê do endereço
  return valor.length <= TAMANHO_MAXIMO && lerNumero(valor) !== null;
}

export function lerDoEndereco<T extends Campos>(busca: string, exemplo: T, opcoes: Opcoes<T> = {}, prefixo = ""): T {
  const parametros = new URLSearchParams(busca);
  const lido: Campos = { ...exemplo };
  for (const chave of Object.keys(exemplo)) {
    const valor = parametros.get(prefixo + chave);
    if (valor !== null && aceita(valor, exemplo[chave], opcoes[chave])) lido[chave] = valor;
  }
  return lido as T;
}

function escreverNoEndereco(campos: Campos, prefixo: string): void {
  const parametros = new URLSearchParams(window.location.search);
  for (const [chave, valor] of Object.entries(campos)) parametros.set(prefixo + chave, valor);
  const { pathname, hash } = window.location;
  window.history.replaceState(window.history.state, "", `${pathname}?${parametros.toString()}${hash}`);
}

/** Os campos da ferramenta, lidos do endereço ao ligar e escritos nele a cada mudança da pessoa.
 * Devolve os campos, `mudar(chave)(valor)` para um campo e `definir(campos)` para vários. */
export function useCamposNoEndereco<T extends Campos>(exemplo: T, opcoes: Opcoes<T> = {}, prefixo = "") {
  const [campos, setCampos] = useState<T>(exemplo);
  const mexeu = useRef(false);
  useEffect(() => {
    if (window.location.search) setCampos(lerDoEndereco(window.location.search, exemplo, opcoes, prefixo));
    // só ao ligar: o exemplo e as opções são constantes de cada ferramenta
  }, []);
  useEffect(() => {
    if (mexeu.current) escreverNoEndereco(campos, prefixo);
  }, [campos, prefixo]);
  const definir = useCallback((novos: T | ((antes: T) => T)) => {
    mexeu.current = true;
    setCampos(novos);
  }, []);
  const mudar = useCallback(
    <K extends keyof T>(chave: K) =>
      (valor: T[K]) =>
        definir((antes) => ({ ...antes, [chave]: valor })),
    [definir],
  );
  return [campos, mudar, definir] as const;
}
