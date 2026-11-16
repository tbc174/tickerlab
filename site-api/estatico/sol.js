// Nascer e pôr do sol para o tema Automático do TickerLab (site e app). Arquivo único: o site serve
// uma cópia e o app o injeta na página. Testado em tests/test_sol.py (pelo Node).
//
// O lugar é a capital do fuso horário do aparelho (Intl), sem pedir a localização a ninguém. Fuso
// sem capital na lista: claro das 6h às 18h no relógio do aparelho.
(function (raiz) {
  "use strict";
  const GRAU = Math.PI / 180;
  const DIA_JULIANO_DA_ERA_UNIX = 2440587.5;
  const J2000 = 2451545;
  const ALTURA_DO_SOL_NO_HORIZONTE = -0.833; // refração e o raio do disco do sol
  const INCLINACAO_DA_TERRA = 23.4397;

  // capital (ou maior cidade) de cada fuso: [latitude, longitude]
  const CAPITAIS = {
    "America/Sao_Paulo": [-23.55, -46.63],
    "America/Bahia": [-12.97, -38.51],
    "America/Fortaleza": [-3.73, -38.52],
    "America/Recife": [-8.05, -34.88],
    "America/Maceio": [-9.67, -35.74],
    "America/Belem": [-1.46, -48.5],
    "America/Araguaina": [-7.19, -48.21],
    "America/Santarem": [-2.44, -54.71],
    "America/Manaus": [-3.12, -60.02],
    "America/Cuiaba": [-15.6, -56.1],
    "America/Campo_Grande": [-20.47, -54.62],
    "America/Porto_Velho": [-8.76, -63.9],
    "America/Boa_Vista": [2.82, -60.67],
    "America/Rio_Branco": [-9.97, -67.81],
    "America/Eirunepe": [-6.66, -69.87],
    "America/Noronha": [-3.85, -32.42],
    "America/New_York": [40.71, -74.01],
    "America/Chicago": [41.88, -87.63],
    "America/Denver": [39.74, -104.99],
    "America/Phoenix": [33.45, -112.07],
    "America/Los_Angeles": [34.05, -118.24],
    "America/Toronto": [43.65, -79.38],
    "America/Mexico_City": [19.43, -99.13],
    "America/Bogota": [4.71, -74.07],
    "America/Lima": [-12.05, -77.04],
    "America/Santiago": [-33.45, -70.67],
    "America/Argentina/Buenos_Aires": [-34.6, -58.38],
    "America/Montevideo": [-34.9, -56.16],
    "America/Asuncion": [-25.26, -57.58],
    "Europe/Lisbon": [38.72, -9.14],
    "Europe/London": [51.51, -0.13],
    "Europe/Madrid": [40.42, -3.7],
    "Europe/Paris": [48.86, 2.35],
    "Europe/Berlin": [52.52, 13.4],
    "Europe/Rome": [41.9, 12.5],
    "Europe/Zurich": [47.38, 8.54],
    "Africa/Luanda": [-8.84, 13.23],
    "Africa/Maputo": [-25.97, 32.57],
    "Asia/Tokyo": [35.68, 139.69],
    "Asia/Shanghai": [31.23, 121.47],
    "Asia/Dubai": [25.2, 55.27],
    "Australia/Sydney": [-33.87, 151.21],
  };

  const paraDiaJuliano = (data) => data.getTime() / 86400000 + DIA_JULIANO_DA_ERA_UNIX;
  const paraData = (diaJuliano) => new Date((diaJuliano - DIA_JULIANO_DA_ERA_UNIX) * 86400000);
  const seno = (graus) => Math.sin(graus * GRAU);

  // Equação do nascer do sol (a base da calculadora da NOAA), com erro de poucos minutos.
  // Devolve as horas em UTC; perto dos polos, `sempre` diz se é dia ou noite o dia todo.
  function nascerEPorDoSol(data, latitude, longitude) {
    const dia = Math.round(paraDiaJuliano(data) - J2000 + 0.0008);
    const meioDiaMedio = dia - longitude / 360;
    const anomalia = (357.5291 + 0.98560028 * meioDiaMedio) % 360;
    const centro = 1.9148 * seno(anomalia) + 0.02 * seno(2 * anomalia) + 0.0003 * seno(3 * anomalia);
    const longitudeDoSol = (anomalia + centro + 180 + 102.9372) % 360;
    const transito = J2000 + meioDiaMedio + 0.0053 * seno(anomalia) - 0.0069 * seno(2 * longitudeDoSol);
    const senoDeclinacao = seno(longitudeDoSol) * seno(INCLINACAO_DA_TERRA);
    const cosDeclinacao = Math.cos(Math.asin(senoDeclinacao));
    const cosAnguloHorario =
      (seno(ALTURA_DO_SOL_NO_HORIZONTE) - seno(latitude) * senoDeclinacao) /
      (Math.cos(latitude * GRAU) * cosDeclinacao);
    if (cosAnguloHorario > 1) return { nascer: null, por: null, sempre: "escuro" };
    if (cosAnguloHorario < -1) return { nascer: null, por: null, sempre: "claro" };
    const meioArco = Math.acos(cosAnguloHorario) / GRAU / 360;
    return { nascer: paraData(transito - meioArco), por: paraData(transito + meioArco), sempre: null };
  }

  // "claro" entre o nascer e o pôr do sol na capital do fuso; "escuro" no resto do dia
  function temaDoMomento(agora, fuso) {
    const capital = CAPITAIS[fuso];
    if (!capital) {
      const hora = agora.getHours();
      return hora >= 6 && hora < 18 ? "claro" : "escuro";
    }
    const sol = nascerEPorDoSol(agora, capital[0], capital[1]);
    if (sol.sempre) return sol.sempre;
    return agora >= sol.nascer && agora < sol.por ? "claro" : "escuro";
  }

  function fusoDoAparelho() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (erro) {
      return "";
    }
  }

  const sol = { CAPITAIS, nascerEPorDoSol, temaDoMomento, fusoDoAparelho };
  if (typeof module !== "undefined" && module.exports) module.exports = sol;
  else raiz.TickerLabSol = sol;
})(typeof window !== "undefined" ? window : globalThis);
