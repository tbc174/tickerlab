# Constantes e caminhos do painel. Nada aqui é segredo: a pasta privada do autor chega por variável de
# ambiente, para o repositório (que é público) não guardar caminho nenhum do PC de ninguém.

$script:VARIAVEL_DA_PASTA_PRIVADA = 'TICKERLAB_PASTA_PRIVADA'
$script:ARQUIVO_DA_FILA = 'projeto-acoes/fila.md'        # dentro da pasta privada
$script:PREFIXO_DA_COPIA = 'analise-acoes'               # cópias: analise-acoes-<mesa>-<tarefa> (CLAUDE.md)
$script:JANELA_DO_TERMINAL = 'tickerlab'                 # todas as abas das conversas numa só janela do wt
$script:TETO_DE_CONVERSAS = 15                           # fila.md: conversas trabalhando ao mesmo tempo
$script:TETO_POR_MESA = 5                                # fila.md: conversas por mesa
$script:TETO_DE_COPIAS = 10                              # ADR 0101: acima disso, apague as de PR mesclado
$script:HORAS_DE_SOSSEGO_APOS_O_MERGE = 2                # a conversa dona ainda pode estar fechando
$script:MODELO_PADRAO = 'sonnet'                         # regra "Economia de tokens": na dúvida, Sonnet
$script:MODELOS = @('sonnet', 'opus', 'fable')           # apelidos que a CLI aceita em --model
$script:TIPOS_DE_RAMO = @('feat', 'fix', 'docs', 'test', 'perf', 'ci', 'chore')
$script:MODOS_DE_PERMISSAO = @('default', 'plan', 'acceptEdits', 'auto')   # nunca o modo que pula as permissões

function Get-PastaPrivada {
    <# Pasta privada do autor (fora do Git), ou $null se a variável de ambiente não está definida. #>
    $pasta = [Environment]::GetEnvironmentVariable($script:VARIAVEL_DA_PASTA_PRIVADA)
    if ([string]::IsNullOrWhiteSpace($pasta)) { return $null }
    return $pasta
}

function Get-ArquivoDaFila {
    <# Caminho do fila.md, ou $null quando a pasta privada não está configurada ou o arquivo não existe. #>
    $pasta = Get-PastaPrivada
    if (-not $pasta) { return $null }
    $arquivo = Join-Path $pasta $script:ARQUIVO_DA_FILA
    if (Test-Path -LiteralPath $arquivo) { return $arquivo }
    return $null
}

function Get-PastaDosLancadores {
    <# Onde `tl nova` grava o prompt e o script da aba: fora da cópia, para não aparecer no git status. #>
    $base = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME '.local/share' }
    Join-Path $base 'TickerLab/terminal'
}

function Get-PastaDasCopias {
    <# A pasta que contém o repositório e as cópias irmãs (analise-acoes-<mesa>-<tarefa>). #>
    Split-Path -Parent $script:RaizDoRepositorio
}

function Get-NomeDoRepositorio {
    <# "dono/repositorio" do remoto origin, para o gh funcionar de qualquer pasta. #>
    if (-not $script:NomeDoRepositorio) {
        $url = @(& git -C $script:RaizDoRepositorio remote get-url origin 2>$null) | Select-Object -First 1
        $script:NomeDoRepositorio = ConvertTo-NomeDoRepositorio ([string]$url)
    }
    $script:NomeDoRepositorio
}

function ConvertTo-NomeDoRepositorio([string]$Url) {
    <# https://github.com/dono/repo.git ou git@github.com:dono/repo.git viram "dono/repo". #>
    if ($Url -match '[:/]([^/:]+/[^/]+?)(\.git)?/?$') { return $Matches[1] }
    throw "Não entendi a URL do remoto: '$Url'"
}

function Test-Ferramenta([string]$Nome) {
    <# Diz se um programa (claude, gh, wt, git) está no PATH. #>
    $null -ne (Get-Command $Nome -ErrorAction SilentlyContinue)
}

function Write-Aviso([string]$Texto) {
    Write-Host "  ! $Texto" -ForegroundColor Yellow
}

function Write-Titulo([string]$Texto) {
    Write-Host $Texto -ForegroundColor Cyan
}
