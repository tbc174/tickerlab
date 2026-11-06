#!/usr/bin/env bash
# Confere o backup do acervo no Drive contra a origem (ADR 0123; linha 251): para cada parte, arquivos e bytes
# na origem e no Drive e `rclone cryptcheck` (compara o hash do arquivo cifrado que o Drive guardou com o que a
# origem geraria; não baixa nada). A origem tem de estar TODA no Drive (o Drive pode ter a mais: arquivo que
# saiu da origem fica, de propósito). Roda na VM do servidor, depois da primeira subida e uma vez por mês.
#
# Saída: uma linha por parte e, no fim, "TOTAL origem ... Drive ...". Sai com 1 e a linha "FALHAS: ..." se
# alguma parte tiver diferença. Não lê nem imprime a senha do crypt.
#
# Variáveis: as mesmas do backup-acervo-drive.sh (ACERVO, PASTA_DE_BACKUPS, PARTES_DO_ACERVO,
# BACKUPS_QUE_SOBEM, RCLONE, RCLONE_CONFIG, REMOTO) mais LOG.
set -uo pipefail
umask 077

ACERVO=${ACERVO:-/mnt/dados/tickerlab-acervo}
PASTA_DE_BACKUPS=${PASTA_DE_BACKUPS:-/mnt/dados/backups}
PARTES_DO_ACERVO=${PARTES_DO_ACERVO-"bruto manifesto ancoras"}
BACKUPS_QUE_SOBEM=${BACKUPS_QUE_SOBEM-"tickerlab tickerlab-pc tickerlab-acervo tickerlab-acessos casa base-antes-manifestos"}
RCLONE=${RCLONE:-$HOME/bin/rclone}
export RCLONE_CONFIG=${RCLONE_CONFIG:-$HOME/.config/tickerlab/backup-drive/rclone.conf}
REMOTO=${REMOTO:-cripto}
LOG=${LOG:-$HOME/logs/conferir-backup-acervo-drive.log}
mkdir -p "$(dirname "$LOG")"

falhas=()
total_arquivos_origem=0
total_bytes_origem=0
total_arquivos_drive=0
total_bytes_drive=0

# numero_do_json CHAVE: pega "count" ou "bytes" da saída de `rclone size --json`.
numero_do_json() {
    sed -n "s/.*\"$1\": *\([0-9]*\).*/\1/p" | head -n 1
}

# conferir NOME ORIGEM DESTINO_NO_REMOTO
conferir() {
    local nome=$1 origem=$2 destino=$3 json_o json_d ao bo ad bd diferencas
    json_o=$("$RCLONE" size "$origem" --json --min-age 5m --exclude "/restrito/**" 2>>"$LOG")
    json_d=$("$RCLONE" size "$REMOTO:$destino" --json 2>>"$LOG")
    ao=$(printf '%s' "$json_o" | numero_do_json count)
    bo=$(printf '%s' "$json_o" | numero_do_json bytes)
    ad=$(printf '%s' "$json_d" | numero_do_json count)
    bd=$(printf '%s' "$json_d" | numero_do_json bytes)
    "$RCLONE" cryptcheck "$origem" "$REMOTO:$destino" --one-way --min-age 5m --exclude "/restrito/**" \
        --combined - 2>>"$LOG" | grep -v '^= ' > "$LOG.diferencas.$$"
    local codigo=${PIPESTATUS[0]}
    diferencas=$(wc -l < "$LOG.diferencas.$$")
    cat "$LOG.diferencas.$$" >> "$LOG"
    rm -f "$LOG.diferencas.$$"
    echo "$nome: origem ${ao:-?} arquivos / ${bo:-?} bytes; Drive ${ad:-?} arquivos / ${bd:-?} bytes; diferenças no cryptcheck: $diferencas (código $codigo)"
    if [ "$codigo" -ne 0 ] || [ "$diferencas" -ne 0 ] || [ -z "$ao" ] || [ -z "$ad" ] || [ "${ad:-0}" -lt "${ao:-1}" ]; then
        falhas+=("$nome")
    fi
    total_arquivos_origem=$((total_arquivos_origem + ${ao:-0}))
    total_bytes_origem=$((total_bytes_origem + ${bo:-0}))
    total_arquivos_drive=$((total_arquivos_drive + ${ad:-0}))
    total_bytes_drive=$((total_bytes_drive + ${bd:-0}))
}

for parte in $PARTES_DO_ACERVO; do
    conferir "acervo-$parte" "$ACERVO/$parte" "acervo/$parte"
done
for pasta in $BACKUPS_QUE_SOBEM; do
    conferir "backups-$pasta" "$PASTA_DE_BACKUPS/$pasta" "backups/$pasta"
done

echo "TOTAL origem $total_arquivos_origem arquivos / $total_bytes_origem bytes; Drive $total_arquivos_drive arquivos / $total_bytes_drive bytes"
if [ "${#falhas[@]}" -gt 0 ]; then
    echo "FALHAS: ${falhas[*]}"
    exit 1
fi
echo "conferência do backup no Drive: tudo certo"
