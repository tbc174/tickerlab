#!/usr/bin/env bash
# Backup cifrado do acervo no Google Drive (ADR 0123; linha 251 da fila). Roda NA VM do servidor de casa
# (a fonte é a VM, nunca a cópia do PC nem o Drive para Desktop), todo dia pelo cron, via rodar-tarefa.sh.
#
# - `rclone copy --backup-dir` datado: copia o que é novo ou mudou; o que mudou ou sumiu da origem NUNCA é
#   apagado do Drive (a versão antiga de um arquivo alterado vai para `_versoes/AAAA-MM-DD/<parte>`).
#   Não existe `sync` aqui: o script não sabe apagar do destino.
# - O destino é um remoto `crypt` (nomes e conteúdo cifrados) sobre uma pasta própria do Drive. A senha e o
#   sal ficam no gerenciador de senhas do Tiago, no cofre `ServidorNotebook-Segredos` e no rclone.conf do
#   servidor (600). Este script não lê nem imprime nenhum dos dois.
# - `restrito/` NÃO sobe (licença de dado, ADR 0115; pode próprio) e a sala de dados também não (documento de
#   cliente): o script recusa qualquer origem com esses nomes.
# - Ritmo limitado (BWLIMIT) para não travar a internet de casa; só um envio por vez (flock): se o anterior
#   ainda está subindo, este sai sem erro e o próximo cron continua de onde parou.
# - Cada parte é independente: se uma falha, as outras ainda sobem. No fim sai com 1 e a linha "FALHAS: ..."
#   (o rodar-tarefa.sh copia a linha para a marca e avisa o monitor push do Kuma).
#
# Variáveis (todas têm padrão): ACERVO, PASTA_DE_BACKUPS, BACKUPS_QUE_SOBEM, PARTES_DO_ACERVO, RCLONE,
# RCLONE_CONFIG, REMOTO, PASTA_DE_VERSOES, BWLIMIT, LOG, DATA_DAS_VERSOES.
set -uo pipefail
umask 077

ACERVO=${ACERVO:-/mnt/dados/tickerlab-acervo}
PASTA_DE_BACKUPS=${PASTA_DE_BACKUPS:-/mnt/dados/backups}
# Partes do acervo que sobem (ADR 0123, item 3). Mais pastas só com o "pode" do Tiago: basta listar aqui.
PARTES_DO_ACERVO=${PARTES_DO_ACERVO-"manifesto ancoras bruto"}
# Pastas de /mnt/dados/backups que sobem. A sala de dados (tickerlab-sala) fica de fora de propósito.
BACKUPS_QUE_SOBEM=${BACKUPS_QUE_SOBEM-"tickerlab tickerlab-pc tickerlab-acervo tickerlab-acessos casa base-antes-manifestos"}
RCLONE=${RCLONE:-$HOME/bin/rclone}
export RCLONE_CONFIG=${RCLONE_CONFIG:-$HOME/.config/tickerlab/backup-drive/rclone.conf}
REMOTO=${REMOTO:-cripto}
PASTA_DE_VERSOES=${PASTA_DE_VERSOES:-_versoes}
# Faixa de horas: de dia sobe devagar, de madrugada solto (a internet de casa fica livre para a casa).
BWLIMIT=${BWLIMIT:-"07:00,4M 23:00,off"}
LOG=${LOG:-$HOME/logs/backup-acervo-drive.log}
DATA_DAS_VERSOES=${DATA_DAS_VERSOES:-$(date +%F)}
NOMES_PROIBIDOS="restrito tickerlab-sala"

mkdir -p "$(dirname "$LOG")"

exec 9>"${TMPDIR:-/tmp}/tickerlab-backup-acervo-drive.lock"
if ! flock -n 9; then
    echo "$(date -Is) o envio anterior ainda está subindo; este sai sem fazer nada"
    exit 0
fi

falhas=()

# Recusa origem que tenha um nome proibido em qualquer pedaço do caminho.
origem_permitida() {
    local origem=$1 nome pedaco
    for nome in $NOMES_PROIBIDOS; do
        for pedaco in ${origem//\// }; do
            [ "$pedaco" = "$nome" ] && return 1
        done
    done
    return 0
}

# subir NOME ORIGEM DESTINO_NO_REMOTO
subir() {
    local nome=$1 origem=$2 destino=$3
    if ! origem_permitida "$origem"; then
        echo "$(date -Is) RECUSADO ($nome): $origem tem nome proibido" | tee -a "$LOG"
        falhas+=("$nome")
        return
    fi
    if [ ! -d "$origem" ]; then
        echo "$(date -Is) FALTA a origem de $nome" | tee -a "$LOG"
        falhas+=("$nome")
        return
    fi
    echo "$(date -Is) início: $nome" >> "$LOG"
    "$RCLONE" copy "$origem" "$REMOTO:$destino" \
        --backup-dir "$REMOTO:$PASTA_DE_VERSOES/$DATA_DAS_VERSOES/$nome" \
        --exclude "/restrito/**" \
        --min-age 5m \
        --bwlimit "$BWLIMIT" \
        --transfers 4 --checkers 8 \
        --drive-chunk-size 128M --drive-stop-on-upload-limit \
        --retries 3 --low-level-retries 20 \
        --stats 10m --stats-one-line --log-level NOTICE --log-file "$LOG"
    local codigo=$?
    if [ "$codigo" -ne 0 ]; then
        echo "$(date -Is) FALHOU: $nome (rclone saiu com $codigo)" >> "$LOG"
        falhas+=("$nome")
    else
        echo "$(date -Is) fim: $nome" >> "$LOG"
    fi
}

# Primeiro o que é pequeno e insubstituível (backups do banco e do PC); o `bruto`, que é o grosso, por último:
# se a internet cair no meio da primeira subida, o importante já está lá.
for pasta in $BACKUPS_QUE_SOBEM; do
    subir "backups-$pasta" "$PASTA_DE_BACKUPS/$pasta" "backups/$pasta"
done
for parte in $PARTES_DO_ACERVO; do
    subir "acervo-$parte" "$ACERVO/$parte" "acervo/$parte"
done

if [ "${#falhas[@]}" -gt 0 ]; then
    echo "FALHAS: ${falhas[*]}"
    exit 1
fi
echo "$(date -Is) backup do acervo no Drive: tudo certo"
