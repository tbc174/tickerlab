# Backup cifrado do acervo no Google Drive

Decisão: ADR 0123 e a Emenda 1 dela, "Empacotar em .tar" (pasta privada do autor). Aqui ficam o desenho, a
rotina e o **passo a passo de restauração**. Nada neste arquivo é segredo: a senha e o sal do `crypt` ficam só
no gerenciador de senhas do autor e em um cofre de segredos dele fora do repositório; a conta do Google e o
Drive não são citados com nome nem endereço.

## O que sobe e o que fica de fora

| Sobe | Como | Para onde (dentro da pasta cifrada) |
|---|---|---|
| `bruto/`, `manifesto/`, `ancoras/` do acervo | pacotes `.tar` | `pacotes/acervo/<parte>/...` (e `indices/...`) |
| Backups em `/mnt/dados/backups`: `tickerlab-pc` (cópia semanal do PC) e `tickerlab-acervo` | pacotes `.tar` | `pacotes/backups/<nome>/...` |
| Backups pequenos: `tickerlab`, `tickerlab-acessos`, `casa`, `base-antes-manifestos` | arquivo a arquivo | `backups/<nome>` |
| Versão antiga de arquivo que mudou (só nos backups pequenos) | `rclone copy --backup-dir` | `_versoes/AAAA-MM-DD/<parte>` |

**Não sobe:** `restrito/` (licença de dado, ADR 0115; só com "pode" próprio) e a sala de dados
(`tickerlab-sala`, documento de cliente). Os scripts recusam essas origens e há teste que cobra.

Também **não sobem** as fontes com nome de pessoa ou só de uso interno (`rfb-cnpj`, `pgfn-divida`,
`mte-lista-suja`, `ibama-autos`, `ibama-embargos`, `cvm-enet-notas`, `antt-autos-de-transito`, `djen-partes`,
`djen-processos`, `datajud`) que ainda estiverem dentro de `bruto/` (o `mover_acervo_restrito` as leva para
`restrito/` quando o autor der o "pode"): o que sobe ao Drive nunca mais sai (LGPD). A poda vale em qualquer
profundidade da árvore (o empacotador nem entra nessas pastas) e há teste que compara a lista com
`acervo.FONTES_COM_PESSOA` e `coletas.FONTES_SO_INTERNAS`.
Outras pastas do acervo (`base/`, `derivados/`, `intradiario/`...) só entram com o "pode" do autor: basta
listá-las em `PARTES_DO_ACERVO` do `scripts/empacotar_acervo_drive.py`.

## Como funciona

- A **fonte é a VM do servidor de casa** (`/mnt/dados/tickerlab-acervo`), nunca a cópia do PC nem o Drive para
  Desktop (que sincroniza e apaga junto).
- `rclone` (MIT) instalado em `~/bin` da VM. Configuração em `~/.config/tickerlab/backup-drive/rclone.conf`
  (permissão 600, fora do Git), com dois remotos: `drive-acervo` (o Drive, com permissão só para arquivos que o
  próprio rclone criou) e `cripto` (`crypt`: **nome de arquivo, de pasta e conteúdo cifrados**) sobre a pasta
  `TickerLab-Backup-Acervo` do Drive.
- **Por que pacotes:** o `client_id` compartilhado do rclone aguenta ~15 arquivos pequenos por minuto no Drive
  (o Google devolve 403 `rateLimitExceeded`) e o acervo tem centenas de milhares. Um `.tar` de várias centenas
  de MB sobe a ~20 MiB/s sem bater nesse limite.
- `scripts/backup-acervo-drive.sh` roda todo dia às 3h15 pelo cron (via `rodar-tarefa.sh`). Primeiro os backups
  pequenos (arquivo a arquivo, `rclone copy --backup-dir`), depois chama `scripts/empacotar_acervo_drive.py subir`.
  **Nada é apagado, movido nem sobrescrito no Drive** (não existe `sync`, `delete`, `move` nem `purge` nos
  scripts; há teste que cobra). Ritmo limitado de dia (`BWLIMIT`, 4 MiB/s das 7h às 23h, solto de madrugada).
  Um envio por vez (trava `flock`): se o anterior ainda sobe, o seguinte sai sem erro.
- Se algo falha, o script termina com a linha `FALHAS: ...` e o `rodar-tarefa.sh` marca a falha (o vigia das
  coletas e o Kuma avisam). O envio de um pacote só vale se o rclone terminou bem **e** o tamanho no Drive bate;
  um envio que quebra no meio nunca vira objeto no Drive.
- O Drive limita o envio a ~750 GB por dia; o rclone para sozinho nesse limite e o cron continua no dia seguinte.

### Os pacotes

- Um pacote reúne os arquivos de **uma fonte e um período**: `bruto/<fonte>/<ano>` para anos fechados e
  `bruto/<fonte>/<ano>-<mês>` para o ano corrente; `manifesto` e `ancoras` ficam em `_tudo`; os backups, uma
  pasta por subpasta. Passou de 20 GiB, divide (`-p1`, `-p2`...).
- Nome no Drive: `pacotes/<destino>/<grupo>/AAAA-MM-DD_HHMMSS.tar` (a data é a do envio). **Um pacote enviado
  nunca é reescrito.** Arquivo novo ou que mudou na origem (tamanho ou data) sobe em um **pacote novo** ("delta")
  na execução seguinte; a versão antiga continua no pacote antigo. Por isso a pasta cresce, nunca encolhe.
- Ao lado de cada pacote vai um **índice** cifrado igual (`indices/<mesmo caminho>.jsonl`): uma linha por
  arquivo, com caminho, bytes, `sha256`, data de modificação e `o` (onde os dados do arquivo começam dentro do
  `.tar`). É ele que permite conferir e restaurar **um arquivo só** sem baixar o pacote inteiro.
- O estado local (`~/.config/tickerlab/backup-drive/pacotes-estado.jsonl`) só diz o que já subiu; se for
  perdido, `empacotar_acervo_drive.py reconstruir-estado` o refaz lendo os índices do Drive.

## Conferência (depois da primeira subida e todo mês)

`scripts/conferir-backup-acervo-drive.sh` (cron: dia 3, 10h) chama `empacotar_acervo_drive.py conferir`:

- por parte, **arquivos e bytes na origem × no Drive** (o Drive pelos índices); passa quando **toda a origem está
  no Drive**; só olha arquivos com mais de 7 horas, para o que foi coletado depois do envio não acusar falta;
- confere que cada pacote do estado existe no Drive com o tamanho do índice;
- o sha256 da conferência mensal vem pela **amostra de restauração** (abaixo, também mensal); a leitura inteira é
  manual (a cada três meses e sempre antes de apagar algo do PC), porque baixa o acervo todo do Drive;
- `conferir --completo` (manual, depois da primeira subida e de vez em quando) **baixa e relê todos os pacotes**
  (sem gravar em disco), recalcula o `sha256` de cada arquivo e compara com o índice **e** com a origem. É o
  equivalente ao `cryptcheck`, que não serve com pacotes.

Os backups pequenos (arquivo a arquivo) seguem com `rclone size` e `rclone cryptcheck`.

## Teste de restauração (todo mês)

`scripts/testar-restauracao-drive.sh` (cron: dia 3, 13h) chama `empacotar_acervo_drive.py amostra`: baixa alguns
**pacotes inteiros** e alguns **arquivos avulsos** (pelo índice), decifra e compara o **sha256** com a origem.
Falhou um: a marca de falha avisa.

## Restaurar (passo a passo)

Cenário: a VM e o PC se perderam. Você precisa de **(1)** a conta do Google do plano, **(2)** a senha e o sal do
`crypt` (gerenciador de senhas ou cofre) e **(3)** qualquer máquina com o `rclone` (rclone.org, MIT) e o `tar`.

1. Instale o `rclone` e rode `rclone config`.
2. Crie o remoto `drive-acervo`: tipo `drive`, escopo **`drive.file`** (acesso só a arquivos criados pelo
   rclone), e autorize com o login Google no navegador.
3. Crie o remoto `cripto`: tipo `crypt`, `remote = drive-acervo:TickerLab-Backup-Acervo`, nomes de arquivo
   `standard`, nomes de pasta cifrados (`true`), e informe a **senha** (`password`) e o **sal** (`password2`)
   guardados. Com a senha ou o sal errados o rclone lista nomes embaralhados e nada abre.
4. Veja o que há: `rclone lsd cripto:` (deve mostrar `pacotes`, `indices`, `backups`, `_versoes`).
   `rclone lsf -R cripto:indices/acervo/bruto/cvm-dfp` lista os índices de uma fonte.
5. **Restaurar um pacote inteiro** (a pasta de destino já com o caminho original):
   `rclone cat cripto:pacotes/acervo/bruto/cvm-dfp/2024/AAAA-MM-DD_HHMMSS.tar | tar -x -C /destino`
   (dentro do `.tar` os caminhos já começam em `bruto/...`, `manifesto/...` ou no nome do backup).
   Para restaurar **tudo**, repita para cada `.tar` **que tenha índice** (um `.jsonl` de mesmo caminho em
   `indices/`), em ordem de data; se o mesmo arquivo aparece em dois pacotes, vale o do pacote **mais novo**.
   Um `.tar` sem índice é um envio que foi interrompido (o `conferir` o avisa; nada é apagado do Drive): **não o
   use**, ele pode estar cortado e, sendo o mais novo, sobrescreveria a versão boa.
6. **Restaurar um arquivo só**: ache a linha dele no índice (`rclone cat cripto:indices/<mesmo caminho>.jsonl |
   grep nome-do-arquivo`) e use `o` (início) e `bytes`:
   `rclone cat cripto:pacotes/<caminho>.tar --offset O --count BYTES > arquivo`.
7. Confira: o `sha256sum` do arquivo ou dos arquivos restaurados contra o `sha256` do índice.
8. Backups pequenos: `rclone copy cripto:backups/<nome> /destino/<nome>`; versão antiga de um arquivo:
   `rclone ls cripto:_versoes/AAAA-MM-DD/<parte>`.
9. Os arquivos de `backups/` já vêm cifrados com `age` (chave só no PC do autor): o `crypt` é uma segunda
   camada; depois de baixar, abra-os com a chave do `age` como sempre.

Sem a senha e o sal o conteúdo do Drive **não pode ser recuperado por ninguém**. Guarde as duas em dois lugares.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `scripts/backup-acervo-drive.sh` | envio diário: backups pequenos por arquivo e chamada do empacotador |
| `scripts/empacotar_acervo_drive.py` | pacotes `.tar` e índices; `subir`, `conferir [--completo]`, `amostra`, `reconstruir-estado` |
| `scripts/conferir-backup-acervo-drive.sh` | conferência mensal (pacotes e backups pequenos) |
| `scripts/testar-restauracao-drive.sh` | restaura uma amostra, decifra e confere o sha256 |
| `scripts/montar-config-backup-drive.sh` | monta o `rclone.conf` (senha e sal pela entrada padrão) |
| `tests/test_empacotar_acervo_drive.py` | pessoa e `restrito/` fora em qualquer profundidade, pacote imutável, nada apagado, conferência |
| `tests/test_backup_acervo_drive.py` | regras dos scripts bash (só copia, `restrito/` fora, falha de uma parte, envio em andamento) |

## Cuidados

- O Drive aceita duas pastas com o mesmo nome: por isso o empacotador cria as pastas-mãe antes de subir em
  paralelo (se duas subidas criassem `pacotes/` ao mesmo tempo, o rclone enxergaria só uma). Se aparecer
  duplicata, `rclone dedupe --dedupe-mode skip drive-acervo:TickerLab-Backup-Acervo` só une as pastas.
- O `rclone` usa hoje o `client_id` compartilhado dele, que o Google avisa que será aposentado em 2026. Quando
  parar, criar um `client_id` próprio (passo a passo em rclone.org/drive) e autorizar de novo: os arquivos
  continuam lá. Está na fila como linha própria.
- O Drive e o Gemini são da mesma conta Google: por isso o banco continua também no Backblaze B2 (ADR 0123).
