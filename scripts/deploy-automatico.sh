#!/usr/bin/env bash
# Atualiza o TickerLab neste servidor quando há um commit novo na main do GitHub CUJOS TESTES
# PASSARAM (GitHub Actions). Se o app não ficar saudável depois da atualização, volta para a
# versão anterior sozinho.
#
# O servidor só puxa (nada de fora entra nele): roda de tempos em tempos pelo cron do usuário.
#   crontab -e  ->  * * * * * /opt/stacks/tickerlab/scripts/deploy-automatico.sh
#
# Log: ~/deploy-tickerlab.log

set -euo pipefail

PASTA="${TICKERLAB_PASTA:-/opt/stacks/tickerlab}"
REPOSITORIO="${TICKERLAB_REPOSITORIO:-tbc174/tickerlab}"
LOG="${TICKERLAB_LOG_DO_DEPLOY:-$HOME/deploy-tickerlab.log}"
ULTIMO_AVISO="${TICKERLAB_ULTIMO_AVISO:-$HOME/.deploy-tickerlab-ultimo-aviso}"
ESPERA_MAXIMA="${TICKERLAB_ESPERA_MAXIMA:-150}"  # segundos para o app ficar saudável

registrar() { echo "$(date -Is) $*" >> "$LOG"; }

# só uma execução por vez
exec 9>/tmp/tickerlab-deploy.lock
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

# Implanta o commit MAIS NOVO cujos testes já passaram, entre o que está no ar e o último da main.
# Esperar só o último travava o deploy: com várias sessões mesclando, o teste dele quase nunca
# tinha terminado (13/10/2026). Uma consulta só à API (sem token, o limite é 60 por hora).
candidatos="$(git rev-list --first-parent --max-count=100 "$atual..$ultimo")"
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

# um commit que já foi revertido (não ficou saudável) não é tentado de novo
[ "$(cat "$ULTIMO_AVISO" 2>/dev/null || true)" = "$novo:revertido" ] && exit 0

# As tarefas agendadas (coletas, backup) rodam dentro do contêiner que o deploy recria: cada uma
# segura esta trava em modo compartilhado (~/rodar-tarefa.sh). Se alguma estiver rodando, o deploy
# não a mata: espera e tenta de novo no próximo minuto. Enquanto ele implanta, as tarefas que
# começarem esperam por ele. (Em 12/10/2026 um deploy às 7h23 matou a coleta da SEC.)
TRAVA_DAS_TAREFAS="${TICKERLAB_TRAVA_DAS_TAREFAS:-/tmp/tickerlab-tarefas.lock}"
exec 8>"$TRAVA_DAS_TAREFAS"
flock -n 8 || { avisar "esperando as tarefas agendadas terminarem"; exit 0; }

registrar "${atual:0:8} -> ${novo:0:8}: testes passaram, implantando"
git merge --ff-only -q "$novo"

saudavel() {
  curl -fsS --max-time 5 http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1 \
    && curl -fsS --max-time 5 http://127.0.0.1:8000/saude >/dev/null 2>&1
}

subir() { docker compose up -d --build >> "$LOG" 2>&1; }

esperar() {
  local ate=$((SECONDS + ESPERA_MAXIMA))
  while [ "$SECONDS" -lt "$ate" ]; do
    saudavel && return 0
    sleep 5
  done
  return 1
}

if subir && esperar; then
  registrar "${novo:0:8}: implantado e saudável"
  exit 0
fi

registrar "${novo:0:8}: NÃO ficou saudável, voltando para ${atual:0:8}"
git reset -q --hard "$atual"
subir || true
if esperar; then
  registrar "${atual:0:8}: versão anterior restaurada"
else
  registrar "${atual:0:8}: ATENÇÃO, a versão anterior também não ficou saudável"
fi
echo "$novo:revertido" > "$ULTIMO_AVISO"   # não tenta o mesmo commit de novo
exit 1
