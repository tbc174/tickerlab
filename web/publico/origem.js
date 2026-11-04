// web/publico/origem.js — origem do cadastro: quem chega por um link de campanha ganha o cookie
// próprio `tl_origem`, que o app lê no primeiro login (src/origem.py: formato e validação). O login
// do Google apaga os parâmetros da URL, por isso a origem viaja num cookie do domínio do TickerLab.
// Carregado pelo site (moldura) e pelo app (src/app/main.tsx). Nada vai para terceiros: sem pixel,
// sem pedido a servidor algum; o cookie só existe se o endereço trouxer `utm_*` ou `ref`.
(() => {
  "use strict";

  const NOME = "tl_origem";
  const DOMINIO = "tickerlab.com.br";
  const DIAS_DE_VALIDADE = 90; // tempo para a pessoa voltar e se cadastrar
  const SEGUNDOS_POR_DIA = 86400;
  // mesma regra de src/origem.py: minúsculas sem acento, números e hífen, até 60 caracteres;
  // o resto (um e-mail colado num utm_*, espaço, maiúscula) fica de fora, para nada pessoal entrar
  const VALOR_VALIDO = /^[a-z0-9-]{1,60}$/;
  const CAMPOS = [
    ["s", "utm_source"],
    ["m", "utm_medium"],
    ["c", "utm_campaign"],
    ["t", "utm_content"],
    ["r", "ref"],
  ];

  // só a primeira origem fica (o app também nunca troca a que já guardou)
  if (document.cookie.split("; ").some((c) => c.startsWith(NOME + "="))) return;

  const parametros = new URLSearchParams(location.search);
  const partes = [];
  for (const [chave, parametro] of CAMPOS) {
    const valor = parametros.get(parametro);
    if (valor !== null && VALOR_VALIDO.test(valor)) partes.push(chave + "=" + valor);
  }
  if (partes.length === 0) return;
  partes.push("v=" + new Date().toISOString().slice(0, 10)); // dia da 1ª visita

  const atributos = ["Path=/", "Max-Age=" + DIAS_DE_VALIDADE * SEGUNDOS_POR_DIA, "SameSite=Lax"];
  // no site e no app (app.tickerlab.com.br), o mesmo cookie; fora dele (testes, local), só o endereço
  const host = location.hostname;
  if (host === DOMINIO || host.endsWith("." + DOMINIO)) atributos.push("Domain=." + DOMINIO);
  if (location.protocol === "https:") atributos.push("Secure");
  document.cookie = NOME + "=" + encodeURIComponent(partes.join("|")) + "; " + atributos.join("; ");
})();
