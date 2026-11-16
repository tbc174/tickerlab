/* Chat "Pergunte à TickerLab Data" (exemplos). Só cola de tela: as respostas são um roteiro fixo,
   uma por pergunta de exemplo. No produto, a IA escreve a consulta e o número vem da base, com
   fonte, data e licença; pergunta livre recebe o aviso de que o chat ainda não está ligado. */
(function () {
  "use strict";
  var caixa = document.querySelector("[data-chat]");
  if (!caixa) return;
  var campo = caixa.querySelector("[data-chat-campo]");
  var formulario = caixa.querySelector("form");
  var conversa = caixa.querySelector("[data-chat-conversa]");
  var abas = caixa.querySelectorAll("[data-publico]");
  var listas = caixa.querySelectorAll("[data-perguntas]");
  var menosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // roteiro: pergunta de exemplo -> resposta com rastro e a chamada que a produziu
  var ROTEIRO = {
    "Quais contas a Petrobras entregou na DFP de 2024?": {
      texto: "As contas do exercício de 2024 saem uma por linha, com o documento (DFP), a versão e a origem. Cada campo traz a fonte e o dia em que ficou público. Os números vêm da base, nunca da memória da IA: aqui aparecem como ‹valor da fonte›.",
      fatos: [["Fonte", "CVM · DFP (cvm-hist-dfp)"], ["Público desde", "‹data da entrega à CVM›"], ["Licença", "ODbL · citar a CVM"]],
      chamada: "GET /data/v1/companies/33000167000101/financials\n    ?period_end=2024-12-31"
    },
    "Qual é a situação da Petrobras na Receita?": {
      texto: "A situação cadastral do estabelecimento vem do retrato mensal mais novo já público da Receita: situação, data, motivo e mês do retrato. MEI e empresário individual nunca saem.",
      fatos: [["Fonte", "Receita Federal · CNPJ (rfb-cnpj)"], ["Retrato", "‹mês do retrato›"], ["Licença", "CC BY · citar a Receita"]],
      chamada: "GET /data/v1/companies/33000167000101"
    },
    "Quanto um fundo cobra de taxa e como ficam 20 anos com 8% ao ano?": {
      texto: "O custo da taxa só sai se você informar o retorno suposto (<code>assumed_return</code>): a conta é sobre a taxa do cadastro da CVM, com o seu número. Não é previsão de rentabilidade e nada é recomendação de investimento.",
      fatos: [["Fonte", "CVM · cadastro de fundos (cvm-cadastros)"], ["Retorno suposto", "o que você enviou"], ["Licença", "ODbL · citar a CVM"]],
      chamada: "GET /data/v1/funds/{cnpj}?assumed_return=0.08"
    },
    "Monte a chamada em Python para as contas de uma empresa como eram em 30/09/2024.": {
      texto: "Sem biblioteca própria ainda: uma chamada HTTP comum, com a chave no cabeçalho. O parâmetro <code>known_at</code> corta tudo o que ficou público depois do dia.",
      codigo: "import os, requests\n\nr = requests.get(\n    \"https://api.tickerlab.com.br/data/v1/companies/33000167000101/financials\",\n    params={\"known_at\": \"2024-09-30\"},\n    headers={\"Authorization\": \"Bearer \" + os.environ[\"TICKERLAB_CHAVE\"]},\n)\nlinhas = r.json()[\"rows\"]",
      fatos: [["Fonte", "CVM · DFP e ITR"], ["Licença", "ODbL · citar a CVM"]],
      chamada: "GET /data/v1/companies/33000167000101/financials?known_at=2024-09-30"
    },
    "Como pego o que a base sabia em 30/09/2024?": {
      texto: "Acrescente <code>known_at</code> à rota. A resposta devolve só o que já estava público naquele dia; o campo <code>valid_until</code> diz quando cada versão foi trocada por outra. Data no futuro é recusada.",
      fatos: [["Regra", "sem olhar o futuro"], ["Guarda", "cada versão, com o dia em que ficou pública"]],
      chamada: "GET /data/v1/companies/33000167000101/financials?known_at=2024-09-30"
    },
    "Que campos vêm em cada valor da resposta?": {
      texto: "Todo campo vem num envelope: <code>value</code>, <code>source</code>, <code>published_at</code> (o dia em que ficou público) e <code>observed_at</code> (quando o TickerLab o viu, quando a base sabe). No fim, <code>sources</code> traz a licença e a frase de atribuição de cada fonte usada.",
      fatos: [["Datas", "ISO, AAAA-MM-DD"], ["Nomes", "em inglês na API"]],
      chamada: "GET /data/v1/catalog"
    },
    "Consulte várias empresas de uma vez.": {
      texto: "O lote aceita até 100 CNPJs e um <code>known_at</code> para todos. Conta um pedido por CNPJ válido e distinto, e cada item diz o seu estado.",
      codigo: "POST /data/v1/companies/batch\n{ \"cnpjs\": [\"33000167000101\", \"33592510000154\"],\n  \"known_at\": \"2025-04-30\" }",
      fatos: [["Limite", "100 CNPJs por lote"], ["Cota", "um pedido por CNPJ"]],
      chamada: "POST /data/v1/companies/batch"
    },
    "Quanto da minha cota do mês já usei?": {
      texto: "A rota de consumo mostra o mês, os pedidos feitos, os negados, o plano e quanto falta. Ela não gasta cota, mas conta no limite por minuto.",
      fatos: [["Cota", "por organização; as chaves dela dividem"]],
      chamada: "GET /data/v1/usage"
    },
    "Que dados a API não entrega?": {
      texto: "Preços e índices da B3 (sem licença), qualquer dado de pessoa física e tabelas cuja fonte não autoriza redistribuir. Um dado só sai quando a fonte permite e a licença vem na resposta; o que é negado responde <code>not_available</code>, igual a um CNPJ que não existe.",
      fatos: [["Padrão", "negar"], ["Resposta", "not_available"]],
      chamada: "GET /data/v1/catalog"
    }
  };
  var SEM_ROTEIRO = "O chat com IA ainda não está ligado: por enquanto só as perguntas de exemplo têm resposta. Quando ligar, a pergunta vira uma consulta à base e a resposta vem sempre com fonte, data e licença.";

  function escapar(s) { return s.replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }

  function balao(classe, html) {
    var el = document.createElement("div");
    el.className = "msg " + classe;
    el.innerHTML = html;
    conversa.appendChild(el);
    conversa.hidden = false;
    return el;
  }

  function htmlDaResposta(r) {
    var h = "<p>" + r.texto + "</p>";
    if (r.codigo) h += '<pre class="chat-codigo"><code>' + escapar(r.codigo) + "</code></pre>";
    if (r.fatos) h += "<dl class=\"chat-fatos\">" + r.fatos.map(function (f) { return "<div><dt>" + f[0] + "</dt><dd>" + f[1] + "</dd></div>"; }).join("") + "</dl>";
    h += '<div class="chat-chamada"><span>chamada que respondeu</span><pre><code>' + escapar(r.chamada) + "</code></pre>" +
      '<button type="button" data-copiar>Copiar</button></div>';
    return h;
  }

  function responder(pergunta) {
    var r = ROTEIRO[pergunta];
    var pensando = balao("ia pensando", "<span></span><span></span><span></span>");
    var espera = menosMovimento ? 0 : 700;
    setTimeout(function () {
      pensando.classList.remove("pensando");
      pensando.innerHTML = r ? htmlDaResposta(r) : "<p>" + SEM_ROTEIRO + "</p>";
      conversa.scrollTop = conversa.scrollHeight;
    }, espera);
  }

  function perguntar(pergunta) {
    pergunta = pergunta.trim();
    if (!pergunta) return;
    balao("eu", "<p>" + escapar(pergunta) + "</p>");
    campo.value = "";
    responder(pergunta);
  }

  formulario.addEventListener("submit", function (e) { e.preventDefault(); perguntar(campo.value); });
  campo.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); perguntar(campo.value); }
  });

  // perguntas prontas: escreve no campo e envia
  caixa.addEventListener("click", function (e) {
    var sugestao = e.target.closest("[data-pergunta]");
    if (sugestao) { perguntar(sugestao.textContent); return; }
    var copiar = e.target.closest("[data-copiar]");
    if (copiar) {
      var texto = copiar.parentNode.querySelector("code").textContent.replace(/\n\s+/g, " ");
      try { navigator.clipboard.writeText(texto).then(function () { copiar.textContent = "Copiado"; setTimeout(function () { copiar.textContent = "Copiar"; }, 1500); }); } catch (erro) { /* sem área de transferência: fica o texto */ }
    }
  });

  // abas de público
  abas.forEach(function (aba) {
    aba.addEventListener("click", function () {
      abas.forEach(function (b) { b.setAttribute("aria-pressed", String(b === aba)); });
      listas.forEach(function (l) { l.hidden = l.dataset.perguntas !== aba.dataset.publico; });
    });
  });

  // o campo vazio vai mostrando exemplos, como convite
  var exemplos = Object.keys(ROTEIRO), i = 0;
  function trocarExemplo() {
    if (document.activeElement === campo || campo.value) return;
    i = (i + 1) % exemplos.length;
    campo.placeholder = "Experimente: “" + exemplos[i] + "”";
  }
  campo.placeholder = "Experimente: “" + exemplos[0] + "”";
  if (!menosMovimento) setInterval(trocarExemplo, 4500);

  // o botão flutuante some enquanto a própria seção do chat está na tela
  var flutuante = document.querySelector(".chat-flutuante");
  if (flutuante && "IntersectionObserver" in window) {
    new IntersectionObserver(function (es) { flutuante.classList.toggle("escondido", es[0].isIntersecting); }, { threshold: 0.15 }).observe(caixa);
  }
})();
