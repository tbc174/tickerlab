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
PARTES_DO_ACERVO=${PARTES_DO_ACERVO-""}
# O acervo vai em pacotes: o empacotador baixa alguns pacotes inteiros e arquivos avulsos (pelo índice), decifra
# e confere o sha256 contra a origem. Vazio desliga.
EMPACOTADOR=${EMPACOTADOR-"python3 $HOME/bin/empacotar_acervo_drive.py"}
RCLONE=${RCLONE:-$HOME/bin/rclone}
export RCLONE_CONFIG=${RCLONE_CONFIG:-$HOME/.config/tickerlab/backup-drive/rclone.conf}
REMOTO=${REMOTO:-cripto}
TAMANHO_DA_AMOSTRA=${TAMANHO_DA_AMOSTRA:-15}
TAMANHO_MAXIMO=${TAMANHO_MAXIMO:-100M}
# Só sorteia arquivo com idade para já ter subido (ver conferir-backup-acervo-drive.sh).
MIN_IDADE=${MIN_IDADE:-7h}
LOG=${LOG:-$HOME/logs/testar-restauracao-drive.log}
mkdir -p "$(dirname "$LOG")"

# Fontes cujo original traz nome de pessoa ou é só de uso interno (`acervo.FONTES_COM_PESSOA` e
# `coletas.FONTES_SO_INTERNAS`): o lugar delas é `restrito/`, mas enquanto o `mover_acervo_restrito` não rodou
# ainda há cópia delas em `bruto/`. Não sobem de jeito nenhum (LGPD: o que sobe nunca mais sai do Drive).
# Há teste que compara esta lista com a do código.
FONTES_SO_NO_RESTRITO="rfb-cnpj pgfn-divida mte-lista-suja ibama-autos ibama-embargos cvm-enet-notas antt-autos-de-transito djen-partes djen-processos datajud"
# Filtros sem âncora: valem em qualquer profundidade da origem, não só na raiz.
FILTROS_DE_EXCLUSAO=(--exclude "restrito/**" --exclude "tickerlab-sala/**")
for fonte in $FONTES_SO_NO_RESTRITO; do
    FILTROS_DE_EXCLUSAO+=(--exclude "$fonte/**")
done

temporaria=$(mktemp -d)
trap 'rm -rf "$temporaria"' EXIT

pacotes_com_problema=0
if [ -n "${EMPACOTADOR// /}" ]; then
    export ACERVO RCLONE REMOTO
    # shellcheck disable=SC2086
    $EMPACOTADOR amostra 2>>"$LOG" | grep -v '^FALHAS:'
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        pacotes_com_problema=1
    fi
fi

lista="$temporaria/lista.txt"
: > "$lista"
for parte in $PARTES_DO_ACERVO; do
    "$RCLONE" lsf -R --files-only --max-size "$TAMANHO_MAXIMO" --min-age "$MIN_IDADE" "${FILTROS_DE_EXCLUSAO[@]}" "$ACERVO/$parte" 2>>"$LOG" \
        | sed "s|^|$parte/|" >> "$lista"
done
if [ ! -s "$lista" ]; then
    if [ -n "${EMPACOTADOR// /}" ]; then
        # só pacotes: o resultado é o da amostra do empacotador
        if [ "$pacotes_com_problema" -ne 0 ]; then
            echo "FALHAS: restauracao-drive"
            exit 1
        fi
        exit 0
    fi
    echo "FALHAS: sem arquivo para testar"
    exit 1
fi

baixados=0
falhas=$pacotes_com_problema
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
