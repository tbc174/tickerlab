#!/usr/bin/env bash
# Monta o rclone.conf do backup do acervo no Drive (ADR 0123; linha 251): o remoto do Drive (com o token que o
# `rclone authorize` gravou) e o remoto `cripto` (crypt: nomes e conteúdo cifrados) por cima de uma pasta própria.
#
# A senha e o sal do crypt chegam PELA ENTRADA PADRÃO (duas linhas: senha e sal), nunca por argumento nem por
# variável, e são passadas por `rclone obscure -`; este script não imprime nenhum deles. Quem alimenta a entrada
# é o PowerShell do Tiago, que lê o arquivo do cofre de segredos dele:
#   $linhas = Get-Content $cofre | ? { $_ -match '^(SENHA|SAL)' } | % { ($_ -split ':\s*',2)[1] }
#   $linhas | wsl -d <distro> -- bash <este script> <arquivo-do-token>
#
# Uso: montar-config-backup-drive.sh ARQUIVO_DO_TOKEN   (a saída do `rclone authorize`)
# Cria ~/.config/tickerlab/backup-drive/rclone.conf (600). Não sobrescreve um rclone.conf que já exista,
# a não ser com SUBSTITUIR=1.
set -euo pipefail
umask 077

RCLONE=${RCLONE:-$HOME/bin/rclone}
PASTA=${PASTA:-$HOME/.config/tickerlab/backup-drive}
PASTA_NO_DRIVE=${PASTA_NO_DRIVE:-TickerLab-Backup-Acervo}
ARQUIVO_DO_TOKEN=${1:?uso: montar-config-backup-drive.sh ARQUIVO_DO_TOKEN}
CONFIG="$PASTA/rclone.conf"

if [ -e "$CONFIG" ] && [ "${SUBSTITUIR:-0}" != 1 ]; then
    echo "já existe $CONFIG; use SUBSTITUIR=1 para refazer" >&2
    exit 1
fi

IFS= read -r senha || true
IFS= read -r sal || true
senha=${senha%$'\r'}
sal=${sal%$'\r'}
if [ -z "$senha" ] || [ -z "$sal" ]; then
    echo "faltam a senha e o sal na entrada padrão (duas linhas)" >&2
    exit 1
fi

# A saída do `rclone authorize` traz entre "--->" e "<---" um bloco em base64 com o JSON da configuração;
# o campo "token" dele é o que o remoto do Drive precisa.
token=$(python3 -c '
import base64, json, sys
bloco = sys.stdin.read().split("--->")[1].split("<---")[0].strip()
bloco += "=" * (-len(bloco) % 4)
print(json.loads(base64.b64decode(bloco))["token"])
' < "$ARQUIVO_DO_TOKEN" 2>/dev/null || true)
if [ -z "$token" ]; then
    echo "não achei o token em $ARQUIVO_DO_TOKEN" >&2
    exit 1
fi

senha_ofuscada=$(printf '%s' "$senha" | "$RCLONE" obscure -)
sal_ofuscado=$(printf '%s' "$sal" | "$RCLONE" obscure -)

mkdir -p "$PASTA"
cat > "$CONFIG" <<CONF
[drive-acervo]
type = drive
scope = drive.file
token = $token

[cripto]
type = crypt
remote = drive-acervo:$PASTA_NO_DRIVE
filename_encryption = standard
directory_name_encryption = true
password = $senha_ofuscada
password2 = $sal_ofuscado
CONF
chmod 600 "$CONFIG"
echo "rclone.conf montado em $CONFIG (remotos: drive-acervo e cripto)"
