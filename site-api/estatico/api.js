/* TickerLab Data: abas do exemplo do hero e a demonstração "como era na data".
   Só cola de tela: nenhum dado é calculado aqui; as três respostas são exemplos fixos que o
   site de verdade deve ler da base (marcados para conferir antes de publicar). */
(function () {
  "use strict";

  // abas curl / Python / JavaScript / Resposta
  var abas = document.querySelectorAll("[data-aba]");
  abas.forEach(function (botao) {
    botao.addEventListener("click", function () {
      abas.forEach(function (b) { b.setAttribute("aria-pressed", String(b === botao)); });
      document.querySelectorAll("[data-painel]").forEach(function (p) { p.hidden = p.dataset.painel !== botao.dataset.aba; });
    });
  });

  // "como era na data": três instantes, três respostas (valores da fonte ficam como marcador)
  var instantes = [
    { data: "2024-03-31", nome: "março de 2024",
      explica: "Antes da DFP 2024: o último anual público é o de 2023, e o de 2024 ainda não existe.",
      resposta: { document: "DFP", reference_period: "2023-12-31", revision: 1, published_at: "2024-03-07", valid_until: "2025-02-27" } },
    { data: "2024-09-30", nome: "setembro de 2024",
      explica: "Durante o ano: o mais novo é o ITR do 2º trimestre; o anual de 2023 segue valendo.",
      resposta: { document: "ITR", reference_period: "2024-06-30", revision: 1, published_at: "2024-08-08", valid_until: "2024-11-07" } },
    { data: "2025-04-30", nome: "abril de 2025",
      explica: "Depois da DFP 2024: o valor anual do exercício de 2024 já está público.",
      resposta: { document: "DFP", reference_period: "2024-12-31", revision: 1, published_at: "2025-02-27", valid_until: null } }
  ];
  var controle = document.getElementById("data-vista");
  if (!controle) return;
  var saida = document.querySelector("[data-resposta-como-era]");
  var nome = document.querySelector("[data-data-escolhida]");
  var explica = document.querySelector("[data-data-explica]");
  var param = document.querySelector("[data-data-param]");

  function texto(valor) {
    if (valor === null) return '<span class="s">null</span>';
    if (typeof valor === "number") return '<span class="n">' + valor + "</span>";
    return '<span class="s">"' + valor + '"</span>';
  }
  function chave(k) { return '<span class="k">"' + k + '"</span>'; }

  function mostrar() {
    var i = instantes[Number(controle.value)] || instantes[instantes.length - 1];
    var r = i.resposta;
    nome.textContent = i.nome;
    explica.textContent = i.explica;
    param.textContent = i.data;
    saida.innerHTML = "{\n  " + chave("document") + ": " + texto(r.document) + ", " + chave("reference_period") + ": " + texto(r.reference_period) +
      ",\n  " + chave("revision") + ": " + texto(r.revision) +
      ",\n  " + chave("published_at") + ": " + texto(r.published_at) + ", " + chave("valid_until") + ": " + texto(r.valid_until) +
      ",\n  " + chave("value") + ': <span class="n">&lt;valor da fonte&gt;</span>\n}';
  }
  controle.addEventListener("input", mostrar);
  mostrar();
})();
