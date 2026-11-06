# Backup cifrado do acervo no Google Drive

Decisão: ADR 0123 (pasta privada do autor). Aqui ficam o desenho, a rotina e o **passo a passo de restauração**.
Nada neste arquivo é segredo: a senha e o sal do `crypt` ficam só no gerenciador de senhas do autor e no cofre
`ServidorNotebook-Segredos`; a conta do Google e o Drive não são citados com nome nem endereço.

## O que sobe e o que fica de fora

| Sobe | Para onde (dentro da pasta cifrada) |
|---|---|
| `bruto/`, `manifesto/`, `ancoras/` do acervo | `acervo/bruto`, `acervo/manifesto`, `acervo/ancoras` |
| Backups cifrados em `/mnt/dados/backups`: `tickerlab`, `tickerlab-pc` (cópia semanal do PC), `tickerlab-acervo`, `tickerlab-acessos`, `casa`, `base-antes-manifestos` | `backups/<nome>` |
| Versão antiga de arquivo que mudou | `_versoes/AAAA-MM-DD/<parte>` |

**Não sobe:** `restrito/` (licença de dado, ADR 0115; só com "pode" próprio) e a sala de dados
(`tickerlab-sala`, documento de cliente). Os scripts recusam essas origens e há teste que cobra.

Também **não sobem** as fontes com nome de pessoa ou só de uso interno (`rfb-cnpj`, `pgfn-divida`, `mte-lista-suja`,
`ibama-autos`, `ibama-embargos`, `cvm-enet-notas`, `antt-autos-de-transito`, `djen-partes`, `djen-processos`,
`datajud`) que ainda estiverem dentro de `bruto/` (o `mover_acervo_restrito` as leva para `restrito/` quando o
autor der o "pode"): o que sobe ao Drive nunca mais sai (LGPD). Os filtros valem em qualquer profundidade e há
teste que compara a lista com `acervo.FONTES_COM_PESSOA` e `coletas.FONTES_SO_INTERNAS`.
Outras pastas do acervo (`base/`, `derivados/`, `intradiario/`...) só entram com o "pode" do autor: basta
listá-las em `PARTES_DO_ACERVO`.

## Como funciona

- A **fonte é a VM** `tickerlab-servidor` (`/mnt/dados/tickerlab-acervo`), nunca a cópia do PC nem o Drive para
  Desktop (que sincroniza e apaga junto).
- `rclone` (MIT) instalado em `~/bin` da VM. Configuração em `~/.config/tickerlab/backup-drive/rclone.conf`
  (permissão 600, fora do Git), com dois remotos: `drive-acervo` (o Drive, com permissão só para arquivos que o
  próprio rclone criou) e `cripto` (`crypt`: **nome de arquivo, de pasta e conteúdo cifrados**) sobre a pasta
  `TickerLab-Backup-Acervo` do Drive.
- `scripts/backup-acervo-drive.sh` roda todo dia às 3h15 pelo cron (via `rodar-tarefa.sh`). Usa só
  `rclone copy --backup-dir`: copia o que é novo ou mudou; o que mudou vai para `_versoes/`; **nada é apagado do
  Drive** (não existe `sync` no script). Ritmo limitado de dia (`BWLIMIT`, padrão 4 MiB/s das 7h às 23h, solto de
  madrugada). Um envio por vez (trava `flock`): se o anterior ainda sobe, o seguinte sai sem erro.
- Cada parte é independente; se alguma falha, o script termina com a linha `FALHAS: ...` e o `rodar-tarefa.sh`
  marca a falha (o vigia das coletas e o Kuma avisam).
- O Drive limita o envio a ~750 GB por dia; o script para sozinho nesse limite e continua no dia seguinte.

## Conferência (depois da primeira subida e todo mês)

`scripts/conferir-backup-acervo-drive.sh` (cron: dia 3, 10h): por parte, arquivos e bytes na origem e no Drive e
`rclone cryptcheck` (compara o hash do arquivo cifrado guardado no Drive com o que a origem geraria, sem
baixar nada). Passa quando **toda a origem está no Drive** e nenhuma diferença aparece. Só confere arquivos com mais de 7 horas
(`MIN_IDADE`), para o que foi coletado depois do envio das 3h15 não acusar falta à toa.

## Teste de restauração (todo mês)

`scripts/testar-restauracao-drive.sh` (cron: dia 3, 13h) baixa uma amostra aleatória de 15 arquivos (até
100 MB cada), decifra e compara o **sha256** com a origem. Falhou um: a marca de falha avisa.

## Restaurar (passo a passo)

Cenário: a VM e o PC se perderam. Você precisa de **(1)** a conta do Google do plano, **(2)** a senha e o sal do
`crypt` (gerenciador de senhas ou cofre) e **(3)** qualquer máquina com o `rclone` (rclone.org, MIT).

1. Instale o `rclone` e rode `rclone config`.
2. Crie o remoto `drive-acervo`: tipo `drive`, escopo **`drive.file`** (acesso só a arquivos criados pelo
   rclone), e autorize com o login Google no navegador.
3. Crie o remoto `cripto`: tipo `crypt`, `remote = drive-acervo:TickerLab-Backup-Acervo`, nomes de arquivo
   `standard`, nomes de pasta cifrados (`true`), e informe a **senha** (`password`) e o **sal** (`password2`)
   guardados. Com a senha ou o sal errados o rclone lista nomes embaralhados e nada abre.
4. Veja o que há: `rclone lsd cripto:` (deve mostrar `acervo`, `backups`, `_versoes`).
5. Baixe: `rclone copy cripto:acervo/bruto /destino/bruto --transfers 4 --progress` (e o mesmo para
   `manifesto`, `ancoras` e `backups/<nome>`).
6. Confira: `rclone size cripto:acervo/bruto` e `rclone size /destino/bruto` (mesmos arquivos e bytes) e, por
   amostra, `sha256sum` contra os `manifesto/` do acervo.
7. Versão antiga de um arquivo: `rclone ls cripto:_versoes/AAAA-MM-DD/<parte>`.
8. Os arquivos de `backups/` já vêm cifrados com `age` (chave só no PC do autor): o `crypt` é uma segunda
   camada; depois de baixar, abra-os com a chave do `age` como sempre.

Sem a senha e o sal o conteúdo do Drive **não pode ser recuperado por ninguém**. Guarde as duas em dois lugares.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `scripts/backup-acervo-drive.sh` | envio diário (cópia com versões) |
| `scripts/conferir-backup-acervo-drive.sh` | contagem origem × Drive e `cryptcheck` |
| `scripts/testar-restauracao-drive.sh` | baixa uma amostra, decifra e confere o sha256 |
| `scripts/montar-config-backup-drive.sh` | monta o `rclone.conf` (senha e sal pela entrada padrão) |
| `tests/test_backup_acervo_drive.py` | regras que não podem quebrar (só copia, `restrito/` fora, falha de uma parte) |

## Cuidados

- O `rclone` usa hoje o `client_id` compartilhado dele, que o Google avisa que será aposentado em 2026. Quando
  parar, criar um `client_id` próprio (passo a passo em rclone.org/drive) e autorizar de novo: os arquivos
  continuam lá. Está na fila como linha própria.
- O Drive e o Gemini são da mesma conta Google: por isso o banco continua também no Backblaze B2 (ADR 0123).
