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
novo="$(git rev-parse origin/main)"
[ "$atual" = "$novo" ] && exit 0

# avisa uma vez só por commit (o cron roda a cada minuto)
avisar() {
  if [ "$(cat "$ULTIMO_AVISO" 2>/dev/null || true)" != "$novo:$1" ]; then
    registrar "${novo:0:8}: $1"
    echo "$novo:$1" > "$ULTIMO_AVISO"
  fi
}

resposta="$(curl -fsS --max-time 20 \
  "https://api.github.com/repos/$REPOSITORIO/commits/$novo/check-runs?per_page=100" || true)"
estado="$(printf '%s' "$resposta" | python3 "$PASTA/scripts/estado_do_ci.py")"

case "$estado" in
  ok) ;;
  aguardando) exit 0 ;;                      # tenta de novo no próximo ciclo
  falhou) avisar "testes do GitHub falharam: não implantei"; exit 0 ;;
  *) avisar "não consegui ler o estado dos testes (GitHub fora do ar?)"; exit 0 ;;
esac

registrar "${atual:0:8} -> ${novo:0:8}: testes passaram, implantando"
git merge --ff-only -q origin/main

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
