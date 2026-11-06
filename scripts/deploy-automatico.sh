#!/usr/bin/env bash
# Atualiza o TickerLab neste servidor quando há um commit novo na main do GitHub CUJOS TESTES
# PASSARAM (GitHub Actions). Se o app não ficar saudável depois da atualização, volta para a
# versão anterior sozinho.
#
# O servidor só puxa (nada de fora entra nele): roda de tempos em tempos pelo cron do usuário.
#   crontab -e  ->  * * * * * /opt/stacks/tickerlab/scripts/deploy-automatico.sh
#
# Dois modos: sem argumento (o do cron) ele escolhe o commit, mescla e passa a vez à versão
# recém-mesclada deste mesmo arquivo em `--implantar <commit no ar> <commit novo>`, que sobe os
# contêineres, confere a saúde e reverte se preciso (veja `implantar`).
#
# Log: ~/deploy-tickerlab.log

set -euo pipefail

PASTA="${TICKERLAB_PASTA:-/opt/stacks/tickerlab}"
REPOSITORIO="${TICKERLAB_REPOSITORIO:-tbc174/tickerlab}"
LOG="${TICKERLAB_LOG_DO_DEPLOY:-$HOME/deploy-tickerlab.log}"
ULTIMO_AVISO="${TICKERLAB_ULTIMO_AVISO:-$HOME/.deploy-tickerlab-ultimo-aviso}"
REVERTIDOS="${TICKERLAB_REVERTIDOS:-$HOME/.deploy-tickerlab-revertidos}"  # um commit por linha
TRAVA_DO_DEPLOY="${TICKERLAB_TRAVA_DO_DEPLOY:-/tmp/tickerlab-deploy.lock}"
TRAVA_DAS_TAREFAS="${TICKERLAB_TRAVA_DAS_TAREFAS:-/tmp/tickerlab-tarefas.lock}"
ESPERA_MAXIMA="${TICKERLAB_ESPERA_MAXIMA:-150}"  # segundos para o app ficar saudável
SCRIPT="$PASTA/scripts/deploy-automatico.sh"

registrar() { echo "$(date -Is) $*" >> "$LOG"; }

# --- subir, conferir e reverter (a parte que roda na versão recém-mesclada do script) ----------

# O Streamlit é a versão clássica, em /classico (18/10/2026; src/classico.py): o caminho vem da
# variável que o compose.yaml do commit implantado dá ao serviço. Sem ela, a raiz. Lido a cada
# conferência: na volta para a versão anterior, vale o compose dela.
caminho_do_streamlit() {
  local valor
  valor="$(sed -n 's/^ *STREAMLIT_SERVER_BASE_URL_PATH: *\([^ #]*\).*/\1/p' compose.yaml | head -n 1)"
  valor="${valor#/}"
  valor="${valor%/}"
  if [ -n "$valor" ]; then printf '/%s' "$valor"; fi
}

saudavel() {
  curl -fsS --max-time 5 "http://127.0.0.1:8501$(caminho_do_streamlit)/_stcore/health" >/dev/null 2>&1 \
    && curl -fsS --max-time 5 http://127.0.0.1:8000/saude >/dev/null 2>&1
}

# a imagem leva o commit que está implantado (versão do código; ADR 0055, exigência 13). Vale
# também na volta para a versão anterior: o commit é lido na hora de subir.
subir() { TICKERLAB_VERSAO="$(git rev-parse HEAD)" docker compose up -d --build >> "$LOG" 2>&1; }

esperar() {
  local ate=$((SECONDS + ESPERA_MAXIMA))
  while [ "$SECONDS" -lt "$ate" ]; do
    saudavel && return 0
    sleep 5
  done
  return 1
}

# Um commit que não ficou saudável vai para a lista dos revertidos, e o cron não o tenta de novo.
# Lista própria (não o arquivo do último aviso): em 18/10/2026 um aviso qualquer apagou a marca
# "revertido" e o cron reimplantou, e reverteu, o mesmo commit várias vezes.
marcar_como_revertido() { echo "$1" >> "$REVERTIDOS"; }

# Sobe o commit já mesclado ($2), espera a saúde e, se não vier, volta para o anterior ($1).
implantar() {
  local atual="$1" novo="$2"
  if subir && esperar; then
    registrar "${novo:0:8}: implantado e saudável"
    return 0
  fi
  registrar "${novo:0:8}: NÃO ficou saudável, voltando para ${atual:0:8}"
  git reset -q --hard "$atual"
  subir || true
  if esperar; then
    registrar "${atual:0:8}: versão anterior restaurada"
  else
    registrar "${atual:0:8}: ATENÇÃO, a versão anterior também não ficou saudável"
  fi
  marcar_como_revertido "$novo"
  return 1
}

if [ "${1:-}" = "--implantar" ]; then
  cd "$PASTA"
  implantar "${2:?commit no ar}" "${3:?commit novo}"
  exit $?
fi

# --- modo do cron: escolher o commit, mesclar e passar a vez à versão nova do script -----------

# só uma execução por vez
exec 9>"$TRAVA_DO_DEPLOY"
flock -n 9 || exit 0

cd "$PASTA"
git fetch -q origin main

atual="$(git rev-parse HEAD)"
ultimo="$(git rev-parse origin/main)"
[ "$atual" = "$ultimo" ] && exit 0
novo="$ultimo"  # até a escolha abaixo, os avisos falam do último commit da main

# avisa uma vez só por commit (o cron roda a cada minuto)
avisar() {
  if [ "$(cat "$ULTIMO_AVISO" 2>/dev/null || true)" != "$novo:$1" ]; then
    registrar "${novo:0:8}: $1"
    echo "$novo:$1" > "$ULTIMO_AVISO"
  fi
}

# os commits entre o que está no ar e o último da main, do mais novo para o mais velho, menos os
# que já foram revertidos (não ficaram saudáveis): esses não são tentados de novo
sem_os_revertidos() {
  if [ -s "$REVERTIDOS" ]; then grep -vxF -f "$REVERTIDOS" || true; else cat; fi
}
candidatos="$(git rev-list --first-parent --max-count=100 "$atual..$ultimo" | sem_os_revertidos)"
[ -z "$candidatos" ] && exit 0

# As tarefas agendadas (coletas, backup) rodam dentro do contêiner que o deploy recria: cada uma
# segura esta trava em modo compartilhado (~/rodar-tarefa.sh). Se alguma estiver rodando, o deploy
# não a mata: espera e tenta de novo no próximo minuto. Enquanto ele implanta, as tarefas que
# começarem esperam por ele. (Em 12/10/2026 um deploy às 7h23 matou a coleta da SEC.)
# A trava vem ANTES da consulta ao GitHub: sem token, a API dá 60 consultas por hora, e consultar
# a cada minuto enquanto uma coleta longa segura a trava esgotou a cota (18/10/2026).
exec 8>"$TRAVA_DAS_TAREFAS"
flock -n 8 || { avisar "esperando as tarefas agendadas terminarem"; exit 0; }

# Implanta o commit MAIS NOVO cujos testes já passaram, entre o que está no ar e o último da main.
# Esperar só o último travava o deploy: com várias sessões mesclando, o teste dele quase nunca
# tinha terminado (13/10/2026). Uma consulta só à API (sem token, o limite é 60 por hora).
resposta="$(curl -fsS --max-time 20 \
  "https://api.github.com/repos/$REPOSITORIO/actions/workflows/testes.yml/runs?branch=main&event=push&per_page=100" \
  || true)"
# shellcheck disable=SC2086  # um argumento por commit
read -r alvo estado <<< "$(printf '%s' "$resposta" \
  | python3 "$PASTA/scripts/estado_do_ci.py" --escolher $candidatos)"

if [ "$alvo" = "-" ]; then
  case "$estado" in
    aguardando) exit 0 ;;                    # tenta de novo no próximo ciclo
    falhou) avisar "testes do GitHub falharam: não implantei"; exit 0 ;;
    *) avisar "não consegui ler o estado dos testes (GitHub fora do ar?)"; exit 0 ;;
  esac
fi
novo="$alvo"

registrar "${atual:0:8} -> ${novo:0:8}: testes passaram, implantando"
git merge --ff-only -q "$novo"

# O bash lê o script aos poucos do arquivo aberto no início, e o merge acabou de gravar um arquivo
# novo: daqui em diante, o resto desta execução seria o da versão ANTIGA do script. Em 18/10/2026
# a correção da conferência de saúde (#418) não valeu no próprio deploy e o cron reverteu 8
# commits. Por isso a parte que sobe e confere roda na versão recém-mesclada; as travas (8 e 9)
# são descritores abertos, que o exec passa adiante.
if ! bash -n "$SCRIPT"; then
  registrar "${novo:0:8}: o script de deploy novo não passa na conferência de sintaxe, voltando"
  git reset -q --hard "$atual"
  marcar_como_revertido "$novo"
  exit 1
fi
exec bash "$SCRIPT" --implantar "$atual" "$novo"
