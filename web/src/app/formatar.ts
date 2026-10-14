// Números no estilo brasileiro, iguais aos do Streamlit (src/formatos.py; o teste confere cada caso
// exportado pelo Python, em web/conteudo/formatacao.json).

export const SEM_NUMERO = "—";
const CASAS = 2;

/** `toFixed` com o empate exato arredondado para o par, como o Python (12,125 → "12.12"). */
function fixo(valor: number): string {
  const absoluto = Math.abs(valor);
  // empate exato = (k + 0,5) / 10^CASAS; em binário isso só existe se o número for múltiplo de
  // 1 / 2^(CASAS+1) (multiplicar por potência de 2 é exato). 2,675 não é: vale 2,67499999...
  const emMeios = absoluto * 2 ** (CASAS + 1);
  const empate = Number.isInteger(emMeios) && (emMeios * 5 ** (CASAS + 1)) % 10 === 5;
  let resultado = absoluto.toFixed(CASAS);
  if (empate) {
    const abaixo = Math.floor(absoluto * 10 ** CASAS);
    const par = abaixo % 2 === 0 ? abaixo : abaixo + 1;
    resultado = (par / 10 ** CASAS).toFixed(CASAS);
  }
  const negativo = valor < 0 || Object.is(valor, -0);
  return negativo ? `-${resultado}` : resultado;
}

function semNumero(valor: number | null | undefined): valor is null | undefined {
  return valor === null || valor === undefined || !Number.isFinite(valor);
}

/** Fração em porcentagem: 0.1234 → "12,34%" (ou "+12,34%"); vazio vira um traço. */
export function formatarPct(valor: number | null | undefined, comSinal = false): string {
  if (semNumero(valor)) return SEM_NUMERO;
  const texto = fixo(valor * 100);
  const sinal = comSinal && !texto.startsWith("-") ? "+" : "";
  return `${sinal}${texto}%`.replace(".", ",");
}

/** Número com duas casas: 1.2345 → "1,23" (o Sharpe); vazio vira um traço. */
export function formatarDecimal(valor: number | null | undefined): string {
  if (semNumero(valor)) return SEM_NUMERO;
  return fixo(valor).replace(".", ",");
}

/** O formato de um número: "pct", "pct_com_sinal", "decimal" ou "inteiro" (a parte inteira). */
export function formatar(valor: number | null | undefined, formato: string): string {
  if (formato === "decimal") return formatarDecimal(valor);
  if (formato === "inteiro") return semNumero(valor) ? SEM_NUMERO : String(Math.trunc(valor) || 0);
  return formatarPct(valor, formato === "pct_com_sinal");
}

/** "2026-10-05" → "05/10/2026" (sem fuso: a data vem pronta da API). */
export function formatarData(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** "2026-09-01" → "set/2026" (os meses do Juros e inflação, como no Streamlit). */
export function formatarMes(iso: string): string {
  const [ano, mes] = iso.slice(0, 7).split("-");
  return `${MESES[Number(mes) - 1]}/${ano}`;
}
