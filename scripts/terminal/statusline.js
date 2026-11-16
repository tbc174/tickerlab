#!/usr/bin/env node
// Linha de status do Claude Code com a cara do TickerLab (embaixo da caixa de digitação, no app e no
// terminal). Recebe os dados da sessão em JSON pela entrada padrão e imprime 2 linhas. Roda no PC e não
// gasta tokens. Configurada em ~/.claude/settings.json ("statusLine", comando `node <este arquivo>`);
// campos do JSON: https://code.claude.com/docs/en/statusline
//
// Linha 1: Mesa · tarefa (o nome da conversa) · modelo e esforço · pasta (cópia de trabalho) · ramo do
//          Git (* = mudanças sem commit) · PR com o CI (✓ passou, ✗ falhou, … rodando) · agente
// Linha 2: contexto usado · limite de 5 h e da semana (com a hora em que renova) · cache · custo · fila
//          única (conversas em "Trabalhando agora" / teto)
//
// O repositório é público: nenhum caminho do PC aqui. A fila chega pela variável TICKERLAB_PASTA_PRIVADA
// (a pasta que tem projeto-acoes/fila.md); sem ela, a linha só não mostra a fila. O CI do PR vem do `gh`,
// que é lento (~1 s) demais para rodar a cada atualização: um processo filho desprendido grava um cache em
// disco e a linha lê o cache.
const { execFileSync, spawn } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const COR = {
  verde: "\x1b[32m",
  amarelo: "\x1b[33m",
  vermelho: "\x1b[31m",
  cinza: "\x1b[90m",
  ciano: "\x1b[36m",
  negrito: "\x1b[1m",
  fim: "\x1b[0m",
};
const pinta = (cor, texto) => `${COR[cor]}${texto}${COR.fim}`;
const SEP = pinta("cinza", " · ");

// Teto da fila única (ADR 0101): o mesmo de scripts/terminal/Privado/Configuracao.ps1 e do hook de início.
const TETO_DE_CONVERSAS = 15;
const VAGAS_DE_AVISO = 2; // com 2 vagas ou menos a fila fica amarela
const ARQUIVO_DA_FILA = path.join("projeto-acoes", "fila.md");
const TITULO_DOS_TRABALHANDO = "Trabalhando agora";
const LARGURA_DO_NOME = 48;
const PREFIXO_DA_COPIA = "analise-acoes"; // as cópias se chamam analise-acoes-<mesa>-<tarefa>
const MESAS = {
  diretoria: "Diretoria",
  dados: "Dados",
  plataforma: "Plataforma",
  produto: "Produto",
  marketing: "Marketing",
  financeiro: "Financeiro",
  satelites: "Satélites",
};
const SEGUNDOS_DO_CACHE_DO_PR = 60;
const SEGUNDOS_DE_ESPERA_DO_GH = 15;
const RAMO_PRINCIPAL = "main"; // a main não tem PR: não vale perguntar ao gh
// Estados de verificação do CI, como Get-ResumoDoCI em scripts/terminal/Privado/Leitores.ps1.
const ESTADOS_RUINS = new Set(["FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"]);
const ESTADOS_RODANDO = new Set(["", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "WAITING", "REQUESTED"]);
const COR_DO_CI = { "✓": "verde", "✗": "vermelho", "…": "amarelo" };

function corDoUso(pct, amarelo = 50, vermelho = 80) {
  return pct >= vermelho ? "vermelho" : pct >= amarelo ? "amarelo" : "verde";
}

function barra(pct, largura = 10) {
  const cheios = Math.max(0, Math.min(largura, Math.round((pct / 100) * largura)));
  return "▓".repeat(cheios) + "░".repeat(largura - cheios);
}

function milhares(n) {
  if (n == null) return "?";
  if (n >= 1e6) return `${+(n / 1e6).toFixed(1)}M`.replace(".", ",");
  return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);
}

function horaDaRenovacao(epoch, comDia) {
  if (!epoch) return "";
  const d = new Date(epoch * 1000);
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (!comDia) return hora;
  const dia = d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  return `${dia} ${hora}`;
}

function encurta(texto, largura = LARGURA_DO_NOME) {
  return texto.length <= largura ? texto : `${texto.slice(0, largura - 1).trimEnd()}…`;
}

// ----- nome da conversa -------------------------------------------------------------------------------

function nomePelaPasta(pasta) {
  // analise-acoes-<mesa>-<tarefa> → "Mesa · tarefa"; analise-acoes-<tarefa> → "tarefa"; a pasta principal → "".
  if (!pasta.startsWith(`${PREFIXO_DA_COPIA}-`)) return "";
  const partes = pasta.slice(PREFIXO_DA_COPIA.length + 1).split("-").filter(Boolean);
  if (partes.length === 0) return "";
  const mesa = MESAS[partes[0].toLowerCase()];
  if (!mesa) return partes.join(" ");
  const tarefa = partes.slice(1).join(" ");
  return tarefa ? `${mesa} · ${tarefa}` : mesa;
}

function nomeDaConversa(d) {
  // O nome dado com `claude --name` ou `/rename` (no app, o título da conversa); sem nome, o que a pasta diz.
  const nome = (d.session_name || "").trim();
  if (nome) return encurta(nome);
  return nomePelaPasta(path.basename(d.workspace?.current_dir || d.cwd || ""));
}

// ----- git e PR -------------------------------------------------------------------------------------

function git(pasta) {
  const rodar = (args) =>
    execFileSync("git", ["-C", pasta, ...args], { timeout: 800, stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  try {
    const ramo = rodar(["branch", "--show-current"]) || `(${rodar(["rev-parse", "--short", "HEAD"])})`;
    const sujo = rodar(["status", "--porcelain", "--untracked-files=no"]) ? "*" : "";
    return ramo + sujo;
  } catch {
    return "";
  }
}

function resumoDoCI(verificacoes) {
  // ✓ tudo passou, ✗ algo falhou, … ainda rodando. PR sem verificação ainda conta como rodando: o CI
  // demora uns segundos para aparecer depois do push.
  const lista = (verificacoes || []).filter((v) => v != null);
  if (lista.length === 0) return "…";
  const estados = lista.map((v) => String(v.conclusion ?? v.state ?? v.status ?? ""));
  if (estados.some((e) => ESTADOS_RUINS.has(e))) return "✗";
  if (estados.some((e) => ESTADOS_RODANDO.has(e))) return "…";
  return "✓";
}

function textoDoPR(pr) {
  // `pr` é o que `gh pr view --json number,state,isDraft,statusCheckRollup,mergeStateStatus` devolve.
  if (!pr || !pr.number) return "";
  const numero = `PR #${pr.number}`;
  if (pr.state === "MERGED") return pinta("cinza", `${numero} mesclado`);
  if (pr.state === "CLOSED") return pinta("cinza", `${numero} fechado`);
  const ci = resumoDoCI(pr.statusCheckRollup);
  const partes = [numero];
  if (pr.isDraft) partes.push(pinta("cinza", "rascunho"));
  partes.push(pinta(COR_DO_CI[ci], ci));
  if (pr.mergeStateStatus === "DIRTY") partes.push(pinta("vermelho", "conflito"));
  return partes.join(" ");
}

function arquivoDoCache(pasta) {
  const chave = crypto.createHash("sha1").update(path.resolve(pasta).toLowerCase()).digest("hex").slice(0, 12);
  return path.join(os.tmpdir(), "tickerlab-linha-de-status", `pr-${chave}.json`);
}

function lerCache(arquivo) {
  try {
    return JSON.parse(fs.readFileSync(arquivo, "utf8"));
  } catch {
    return null;
  }
}

function gravarCache(arquivo, dados) {
  fs.mkdirSync(path.dirname(arquivo), { recursive: true });
  const temporario = `${arquivo}.${process.pid}.tmp`;
  fs.writeFileSync(temporario, JSON.stringify(dados));
  fs.renameSync(temporario, arquivo);
}

function prDaPasta(pasta, ramo, agora = Date.now()) {
  // O PR do ramo, pelo cache. Cache velho: um filho desprendido pergunta ao gh e regrava; esta chamada
  // não espera por ele (a linha de status tem de sair na hora).
  if (!pasta || !ramo || ramo === RAMO_PRINCIPAL) return null;
  const arquivo = arquivoDoCache(pasta);
  const cache = lerCache(arquivo) || {};
  const idadeEmSegundos = (agora - (cache.pedidoEm || cache.em || 0)) / 1000;
  if (idadeEmSegundos > SEGUNDOS_DO_CACHE_DO_PR) {
    try {
      gravarCache(arquivo, { ...cache, pedidoEm: agora });
      spawn(process.execPath, [__filename, "--atualizar-pr", pasta], {
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      }).unref();
    } catch {
      // sem cache não há PR na linha; nada mais a fazer
    }
  }
  return cache.pr || null;
}

function atualizarPR(pasta) {
  // Roda no filho: o PR do ramo atual da pasta (null quando não há PR, ou o gh não está instalado).
  let pr = null;
  try {
    const campos = "number,state,isDraft,statusCheckRollup,mergeStateStatus";
    const saida = execFileSync("gh", ["pr", "view", "--json", campos], {
      cwd: pasta,
      timeout: SEGUNDOS_DE_ESPERA_DO_GH * 1000,
      stdio: ["ignore", "pipe", "ignore"],
    });
    pr = JSON.parse(saida.toString());
  } catch {
    pr = null;
  }
  gravarCache(arquivoDoCache(pasta), { em: Date.now(), pr });
}

// ----- fila única -----------------------------------------------------------------------------------

function linhasDaTabela(texto, titulo) {
  // As linhas de dados da tabela logo abaixo de "## titulo" (sem o cabeçalho nem a linha |---|), até a
  // próxima seção. Espelha Read-TabelaMarkdown (painel tl) e linhas_da_tabela (hook de início).
  const linhas = texto.split(/\r?\n/);
  // O título pode ter complemento: "## Trabalhando agora (máximo 15, até 5 por mesa)".
  const cabecalho = `## ${titulo}`;
  const inicio = linhas.findIndex((linha) => {
    const limpa = linha.trim();
    return limpa === cabecalho || (limpa.startsWith(cabecalho) && /\s/.test(limpa[cabecalho.length]));
  });
  if (inicio < 0) return [];
  const dados = [];
  for (const linha of linhas.slice(inicio + 1)) {
    if (linha.startsWith("## ")) break;
    const limpa = linha.trim();
    if (!limpa.startsWith("|") || /^\|\s*:?-/.test(limpa)) continue;
    dados.push(limpa);
  }
  return dados.slice(1);
}

function arquivoDaFila(ambiente = process.env) {
  const pastaPrivada = ambiente.TICKERLAB_PASTA_PRIVADA;
  return pastaPrivada ? path.join(pastaPrivada, ARQUIVO_DA_FILA) : "";
}

function vagasDaFila(arquivo) {
  if (!arquivo) return "";
  let texto;
  try {
    texto = fs.readFileSync(arquivo, "utf8");
  } catch {
    return "";
  }
  const trabalhando = linhasDaTabela(texto, TITULO_DOS_TRABALHANDO).length;
  const cheia = trabalhando >= TETO_DE_CONVERSAS;
  const cor = cheia ? "vermelho" : trabalhando >= TETO_DE_CONVERSAS - VAGAS_DE_AVISO ? "amarelo" : "verde";
  return `fila ${pinta(cor, `${trabalhando}/${TETO_DE_CONVERSAS}${cheia ? " cheia" : ""}`)}`;
}

// ----- as duas linhas -------------------------------------------------------------------------------

function linha1(d) {
  const partes = [];
  const nome = nomeDaConversa(d);
  if (nome) partes.push(pinta("negrito", nome));
  const modelo = d.model?.display_name || d.model?.id || "?";
  const esforco = d.effort?.level ? ` ${d.effort.level}` : "";
  const rapido = d.fast_mode ? " ⚡" : "";
  partes.push(pinta("ciano", `${modelo}${esforco}${rapido}`));
  const pasta = d.workspace?.current_dir || d.cwd || "";
  if (pasta) partes.push(path.basename(pasta));
  const ramo = pasta ? git(pasta) : "";
  if (ramo) partes.push(`⎇ ${ramo}`);
  const pr = prDaPasta(pasta, ramo.replace(/\*$/, "")) || (d.pr?.number ? { number: d.pr.number, state: "OPEN" } : null);
  const textoPR = textoDoPR(pr);
  if (textoPR) partes.push(textoPR);
  if (d.agent?.name) partes.push(`agente ${d.agent.name}`);
  return partes.join(SEP);
}

function linha2(d) {
  const partes = [];
  const cw = d.context_window || {};
  const pct = Math.round(cw.used_percentage ?? 0);
  const u = cw.current_usage || {};
  const usados = (u.input_tokens || 0) + (u.cache_creation_input_tokens || 0) + (u.cache_read_input_tokens || 0);
  const cor = corDoUso(pct, 50, 75);
  partes.push(
    `contexto ${pinta(cor, barra(pct))} ${pinta(cor, `${pct}%`)} ${pinta("cinza", `${milhares(usados)}/${milhares(cw.context_window_size)}`)}`,
  );

  const rl = d.rate_limits || {};
  if (rl.five_hour?.used_percentage != null) {
    const p = Math.round(rl.five_hour.used_percentage);
    partes.push(`5h ${pinta(corDoUso(p, 60, 85), `${p}%`)} ${pinta("cinza", `↻${horaDaRenovacao(rl.five_hour.resets_at, false)}`)}`);
  }
  if (rl.seven_day?.used_percentage != null) {
    const p = Math.round(rl.seven_day.used_percentage);
    partes.push(`semana ${pinta(corDoUso(p, 60, 85), `${p}%`)} ${pinta("cinza", `↻${horaDaRenovacao(rl.seven_day.resets_at, true)}`)}`);
  }

  const pc = d.prompt_cache;
  if (pc?.hit_ratio != null) {
    const p = Math.round(pc.hit_ratio * 100);
    partes.push(`cache ${pinta(pc.warm ? corDoUso(100 - p, 30, 60) : "amarelo", `${p}%${pc.warm ? "" : " frio"}`)}`);
  }

  const custo = d.cost?.total_cost_usd;
  if (custo != null) partes.push(pinta("cinza", `≈US$ ${custo.toFixed(2).replace(".", ",")}`));

  const fila = vagasDaFila(arquivoDaFila());
  if (fila) partes.push(fila);
  return partes.join(SEP);
}

function principal(argumentos) {
  if (argumentos[0] === "--atualizar-pr" && argumentos[1]) {
    atualizarPR(argumentos[1]);
    return;
  }
  let entrada = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (pedaco) => (entrada += pedaco));
  process.stdin.on("end", () => {
    let d = {};
    try {
      d = JSON.parse(entrada || "{}");
    } catch {
      process.stdout.write("linha de status: JSON inválido\n");
      return;
    }
    process.stdout.write(`${linha1(d)}\n${linha2(d)}\n`);
  });
}

module.exports = {
  TETO_DE_CONVERSAS,
  encurta,
  linhasDaTabela,
  nomeDaConversa,
  nomePelaPasta,
  resumoDoCI,
  textoDoPR,
  vagasDaFila,
};

if (require.main === module) principal(process.argv.slice(2));
