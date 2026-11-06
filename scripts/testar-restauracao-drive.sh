#!/usr/bin/env bash
# Teste de restauração do backup do acervo no Drive (ADR 0123; linha 251; mensal pelo cron): baixa uma amostra
# de arquivos do Drive, decifra (o remoto `crypt` decifra ao baixar) e confere o sha256 contra a origem.
# Só passa se TODOS os arquivos da amostra baixarem e baterem. Não escreve nada no Drive nem na origem; a
# amostra vive numa pasta temporária que é apagada no fim.
#
# Variáveis: ACERVO, PARTES_DO_ACERVO, RCLONE, RCLONE_CONFIG, REMOTO, TAMANHO_DA_AMOSTRA (padrão 15 arquivos),
# TAMANHO_MAXIMO (padrão 100M por arquivo), LOG.
set -uo pipefail
umask 077

ACERVO=${ACERVO:-/mnt/dados/tickerlab-acervo}
PARTES_DO_ACERVO=${PARTES_DO_ACERVO-"bruto manifesto ancoras"}
RCLONE=${RCLONE:-$HOME/bin/rclone}
export RCLONE_CONFIG=${RCLONE_CONFIG:-$HOME/.config/tickerlab/backup-drive/rclone.conf}
REMOTO=${REMOTO:-cripto}
TAMANHO_DA_AMOSTRA=${TAMANHO_DA_AMOSTRA:-15}
TAMANHO_MAXIMO=${TAMANHO_MAXIMO:-100M}
LOG=${LOG:-$HOME/logs/testar-restauracao-drive.log}
mkdir -p "$(dirname "$LOG")"

temporaria=$(mktemp -d)
trap 'rm -rf "$temporaria"' EXIT

lista="$temporaria/lista.txt"
for parte in $PARTES_DO_ACERVO; do
    "$RCLONE" lsf -R --files-only --max-size "$TAMANHO_MAXIMO" "$ACERVO/$parte" 2>>"$LOG" \
        | sed "s|^|$parte/|" >> "$lista"
done
if [ ! -s "$lista" ]; then
    echo "FALHAS: sem arquivo para testar"
    exit 1
fi

baixados=0
falhas=0
while IFS= read -r arquivo; do
    destino="$temporaria/baixado"
    rm -rf "$destino"
    if ! "$RCLONE" copyto "$REMOTO:acervo/$arquivo" "$destino" --retries 3 --log-level ERROR --log-file "$LOG"; then
        echo "não baixou: $arquivo" >> "$LOG"
        falhas=$((falhas + 1))
        continue
    fi
    esperado=$(sha256sum "$ACERVO/$arquivo" | cut -d' ' -f1)
    obtido=$(sha256sum "$destino" | cut -d' ' -f1)
    if [ "$esperado" = "$obtido" ]; then
        baixados=$((baixados + 1))
    else
        echo "sha256 diferente: $arquivo" >> "$LOG"
        falhas=$((falhas + 1))
    fi
done < <(shuf -n "$TAMANHO_DA_AMOSTRA" "$lista")

echo "restauração: $baixados arquivos baixados, decifrados e conferidos por sha256; $falhas com problema"
if [ "$falhas" -ne 0 ] || [ "$baixados" -eq 0 ]; then
    echo "FALHAS: restauracao-drive"
    exit 1
fi
