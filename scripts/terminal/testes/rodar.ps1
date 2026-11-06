#Requires -Version 7.0
# Testes do painel `tl`, sem Pester (o PowerShell 7 não o traz e o CI não precisa instalar nada a mais).
# Rode: pwsh -NoProfile -File scripts/terminal/testes/rodar.ps1   (sai com 1 se algum teste falhar).
# As funções privadas do módulo são chamadas dentro do escopo dele: & $modulo { Funcao ... }.

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch { <# saída sem console #> }

$pastaDosTestes = $PSScriptRoot
$exemplos = Join-Path $pastaDosTestes 'exemplos'
Import-Module (Join-Path $pastaDosTestes '../TickerLab.psd1') -Force
$modulo = Get-Module TickerLab

$script:Passaram = 0
$script:Falhas = [System.Collections.Generic.List[string]]::new()

function Teste([string]$Nome, [scriptblock]$Corpo) {
    try {
        & $Corpo
        $script:Passaram++
        Write-Host "  ok     $Nome"
    } catch {
        $script:Falhas.Add($Nome)
        Write-Host "  FALHOU $Nome" -ForegroundColor Red
        Write-Host "         $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Igual($Obtido, $Esperado) {
    if ("$Obtido" -cne "$Esperado") { throw "esperado [$Esperado], obtido [$Obtido]" }
}

function IgualLista($Obtido, $Esperado) {
    Igual (@($Obtido) -join ' | ') (@($Esperado) -join ' | ')
}

function Contem([string]$Texto, [string]$Trecho) {
    if (-not $Texto.Contains($Trecho)) { throw "não contém [$Trecho]:`n$Texto" }
}

function NaoContem([string]$Texto, [string]$Trecho) {
    if ($Texto.Contains($Trecho)) { throw "não devia conter [$Trecho]:`n$Texto" }
}

function Erro([scriptblock]$Corpo) {
    <# A mensagem do erro que o bloco lança; falha se ele não lançar nenhum. #>
    try { & $Corpo } catch { return $_.Exception.Message }
    throw 'esperava um erro e não houve'
}

function Exemplo([string]$Nome) { Get-Content -LiteralPath (Join-Path $exemplos $Nome) -Raw -Encoding utf8 }

Write-Host 'Testes do painel tl'

# --- nomes --------------------------------------------------------------------------------------------------

Teste 'nome simples tira acento, maiúscula e símbolo' {
    Igual (& $modulo { ConvertTo-NomeSimples 'Satélites · TCE-CE coleta' }) 'satelites-tce-ce-coleta'
}

Teste 'nome da cópia segue analise-acoes-<mesa>-<tarefa>' {
    Igual (& $modulo { Get-NomeDaCopia 'Dados' 'TCE-CE coleta' }) 'analise-acoes-dados-tce-ce-coleta'
}

Teste 'Resolve-Mesa aceita qualquer grafia e erra com a lista das mesas' {
    Igual (& $modulo { (Resolve-Mesa 'SATELITES').Nome }) 'Satélites'
    $erro = Erro { & $modulo { Resolve-Mesa 'vendas' } }
    Contem $erro "Mesa desconhecida: 'vendas'"
    Contem $erro 'Diretoria, Dados, Plataforma'
}

Teste 'título da conversa é "Mesa · tarefa"' {
    Igual (& $modulo { Get-TituloDaConversa 'dados' 'TCE-CE coleta' }) 'Dados · TCE-CE coleta'
}

Teste 'ramo segue tipo/tarefa e recusa tipo desconhecido' {
    Igual (& $modulo { Get-NomeDoRamo 'fix' 'Selic sem futuro' }) 'fix/selic-sem-futuro'
    Contem (Erro { & $modulo { Get-NomeDoRamo 'feature' 'x' } }) 'Tipo de ramo desconhecido'
}

Teste 'Get-MesaDoNome lê a mesa do nome da conversa' {
    Igual (& $modulo { Get-MesaDoNome 'Dados · TCE-CE (682)' }) 'Dados'
    Igual (& $modulo { Get-MesaDoNome 'Agente · Recepção do Slack' }) ''
    Igual (& $modulo { Get-MesaDoNome 'sem separador' }) ''
}

Teste 'nomes parecidos: mesma mesa e uma palavra da tarefa em comum' {
    Igual (& $modulo { Test-NomesParecidos 'Dados · layout real do CNES em DBC (684)' 'analise-acoes-dados-cnes-dbc' }) $true
    Igual (& $modulo { Test-NomesParecidos 'Dados · histórico datado do CNPJ (686)' 'analise-acoes-dados-tce-ce' }) $false
    Igual (& $modulo { Test-NomesParecidos 'Produto · CNES na ficha' 'analise-acoes-dados-cnes-dbc' }) $false
}

# --- argumentos ---------------------------------------------------------------------------------------------

Teste 'ConvertTo-Parametros separa posicionais e nomeados' {
    $p = & $modulo { ConvertTo-Parametros @('Dados', 'minha tarefa', '-Modelo', 'sonnet', '-SoMostrar', '-Ramo', 'fix') }
    IgualLista $p.Posicionais @('Dados', 'minha tarefa')
    Igual $p.Nomeados['Modelo'] 'sonnet'
    Igual $p.Nomeados['SoMostrar'] $true
    Igual $p.Nomeados['Ramo'] 'fix'
}

Teste 'argumentos do claude: nome, modelo, permissão e o prompt por último' {
    $a = & $modulo { Get-ArgumentosDoClaude -Nome 'Dados · x' -Modelo 'sonnet' -ModoDePermissao 'plan' -Prompt 'Oi' }
    IgualLista $a @('--name', 'Dados · x', '--model', 'sonnet', '--permission-mode', 'plan', 'Oi')
    $b = & $modulo { Get-ArgumentosDoClaude -Nome 'Dados · x' -Modelo 'opus' -ModoDePermissao 'default' }
    IgualLista $b @('--name', 'Dados · x', '--model', 'opus')
}

Teste 'argumentos do wt: aba nova na janela tickerlab com título, cor e pasta' {
    $a = & $modulo { Get-ArgumentosDoTerminal -Titulo 'Dados · x' -Cor '#3FA37A' -Pasta 'C:\copias\x' -Lancador 'C:\l\abrir.ps1' }
    Igual ($a -join ' ') '-w tickerlab new-tab --title Dados · x --tabColor #3FA37A --suppressApplicationTitle -d C:\copias\x pwsh -NoLogo -NoExit -File C:\l\abrir.ps1'
}

Teste 'lançador entra na cópia, escapa as aspas e abre o claude com o prompt do arquivo' {
    $l = & $modulo {
        Get-ConteudoDoLancador -Titulo "Dados · it's" -Pasta 'C:\copias\x' -ArquivoDoPrompt 'C:\l\prompt.md' `
            -ArgumentosDoClaude @('--name', "Dados · it's", '--model', 'sonnet')
    }
    Contem $l "Set-Location -LiteralPath 'C:\copias\x'"
    Contem $l "`$prompt = Get-Content -LiteralPath 'C:\l\prompt.md' -Raw -Encoding utf8"
    Contem $l "& claude '--name' 'Dados · it''s' '--model' 'sonnet' `$prompt"
}

Teste 'prompt de abertura preenche tudo e cita a passagem' {
    $p = & $modulo {
        Get-PromptDeAbertura -Mesa 'Dados' -Tarefa 'coleta' -Copia 'C:\c\analise-acoes-dados-coleta' -Ramo 'feat/coleta' -Passagem 'passagens/coleta.md'
    }
    NaoContem $p '{{'
    Contem $p 'Mesa Dados: coleta.'
    Contem $p 'ramo `feat/coleta`'
    Contem $p 'Leia a passagem `passagens/coleta.md`'
    Contem $p 'gh pr checks <número> --watch'
    $semPassagem = & $modulo { Get-PromptDeAbertura -Mesa 'Dados' -Tarefa 'coleta' -Copia 'C:\c' -Ramo '' -Passagem '' }
    Contem $semPassagem 'passar-a-vez'
    Contem $semPassagem 'nunca faça commit na main'
}

# --- leitores -----------------------------------------------------------------------------------------------

Teste 'Read-TabelaMarkdown lê a tabela da seção, com \| escapado dentro da célula' {
    $linhas = & $modulo { param($t) Read-TabelaMarkdown -Texto $t -Secao 'Trabalhando agora' } (Exemplo 'fila.md')
    Igual $linhas.Count 2
    Igual $linhas[0].Mesa 'Dados'
    Igual $linhas[1].Item 'A | B'
    Igual (& $modulo { param($t) @(Read-TabelaMarkdown -Texto $t -Secao 'Não existe').Count } (Exemplo 'fila.md')) 0
}

Teste 'Read-Fila separa quem trabalha e a fila, na ordem' {
    $fila = & $modulo { param($t) Read-Fila $t } (Exemplo 'fila.md')
    Igual $fila.Trabalhando.Count 2
    Igual $fila.Fila.Count 3
    Igual $fila.Fila[0].'#' '1'
    Igual $fila.Fila[2].'Depende de' '701'
    Contem (& $modulo { param($r) Format-LinhaDaFila $r } $fila.Fila[0]) 'Dados · coleta nova · Dados · 700: [coleta nova](planos/coleta.md)'
}

Teste 'Read-Sessoes traduz o claude agents --json' {
    $s = @(& $modulo { param($j) Read-Sessoes $j } (Exemplo 'agents.json'))
    Igual $s.Count 3
    Igual $s[0].Situacao 'trabalhando'
    Igual $s[0].Mesa 'Dados'
    Igual $s[1].Situacao 'pergunta'
    Igual $s[1].Esperando 'permission'
    Igual $s[2].Nome '(sem nome)'
    Igual $s[2].Situacao 'parada'
    Igual $s[2].Tipo 'background'
    Igual (& $modulo { @(Read-Sessoes '').Count }) 0
}

Teste 'Read-Copias lê o git worktree list --porcelain' {
    $c = @(& $modulo { param($l) Read-Copias $l } ((Exemplo 'worktrees.txt') -split "`r?`n"))
    Igual $c.Count 3
    Igual $c[0].Ramo 'main'
    Igual $c[1].Nome 'analise-acoes-dados-tce-ce'
    Igual $c[1].Ramo 'feat/tce-ce-coleta'
}

Teste 'Read-PullRequests lê o gh pr list --json' {
    $json = '[{"number": 901, "title": "feat: x", "headRefName": "feat/x", "statusCheckRollup": [{"conclusion": "SUCCESS"}],' +
        ' "isDraft": false, "autoMergeRequest": {"enabledAt": "2026-11-05T10:00:00Z"}, "mergedAt": null},' +
        ' {"number": 900, "title": "fix: y", "headRefName": "fix/y", "statusCheckRollup": [], "isDraft": true,' +
        ' "autoMergeRequest": null, "mergedAt": "2026-11-05T09:00:00Z"}]'
    $prs = @(& $modulo { param($j) Read-PullRequests $j } $json)
    Igual $prs.Count 2
    Igual $prs[0].CI '✓'
    Igual $prs[0].AutoMerge $true
    Igual $prs[0].MescladoEm ''
    Igual $prs[1].CI ''
    Igual $prs[1].Rascunho $true
    if (-not $prs[1].MescladoEm) { throw 'MescladoEm devia estar preenchido' }
}

Teste 'Get-ResumoDoCI resume as verificações' {
    Igual (& $modulo { Get-ResumoDoCI @(@{ conclusion = 'SUCCESS' }, @{ conclusion = 'SUCCESS' }) }) '✓'
    Igual (& $modulo { Get-ResumoDoCI @(@{ conclusion = 'SUCCESS' }, @{ conclusion = 'FAILURE' }) }) '✗'
    Igual (& $modulo { Get-ResumoDoCI @(@{ conclusion = 'SUCCESS' }, @{ status = 'IN_PROGRESS' }) }) '…'
    Igual (& $modulo { Get-ResumoDoCI @(@{ conclusion = ''; status = 'IN_PROGRESS' }) }) '…'
    Igual (& $modulo { Get-ResumoDoCI @() }) ''
    Igual (& $modulo { Get-ResumoDoCI $null }) ''
}

Teste 'Find-CopiasMescladas acha as cópias de PR mesclado e os motivos para esperar' {
    $copias = @(& $modulo { param($l) Read-Copias $l } ((Exemplo 'worktrees.txt') -split "`r?`n"))
    $prs = @(
        [pscustomobject]@{ Numero = 888; Ramo = 'feat/tce-ce-coleta'; MescladoEm = [datetime]'2026-11-05 10:00' }
        [pscustomobject]@{ Numero = 890; Ramo = 'feat/api-ficha-markdown'; MescladoEm = [datetime]'2026-11-05 17:30' }
        [pscustomobject]@{ Numero = 700; Ramo = 'feat/tce-ce-coleta'; MescladoEm = [datetime]'2026-10-01 10:00' }
    )
    $sessoes = @([pscustomobject]@{ Nome = 'Dados · TCE-CE coleta automática (682)' })
    $r = @(& $modulo {
        param($c, $p, $s)
        Find-CopiasMescladas -Copias $c -PullRequestsMesclados $p -Sessoes $s -Agora ([datetime]'2026-11-05 18:00')
    } $copias $prs $sessoes)
    Igual $r.Count 2
    $tce = $r | Where-Object Ramo -eq 'feat/tce-ce-coleta'
    Igual $tce.PR 888
    Contem ($tce.Motivos -join ';') 'conversa aberta parecida: Dados · TCE-CE coleta automática (682)'
    NaoContem ($tce.Motivos -join ';') 'mesclado há menos de'
    $ficha = $r | Where-Object Ramo -eq 'feat/api-ficha-markdown'
    IgualLista $ficha.Motivos @('mesclado há menos de 2 h')
}

Teste 'ConvertTo-NomeDoRepositorio entende https e ssh' {
    Igual (& $modulo { ConvertTo-NomeDoRepositorio 'https://github.com/dono/repo.git' }) 'dono/repo'
    Igual (& $modulo { ConvertTo-NomeDoRepositorio 'git@github.com:dono/repo.git' }) 'dono/repo'
    Igual (& $modulo { ConvertTo-NomeDoRepositorio 'https://github.com/dono/repo' }) 'dono/repo'
}

Teste 'Format-TextoCurto tira link e negrito e corta com …' {
    Igual (& $modulo { Format-TextoCurto '700: [coleta nova](planos/coleta.md) **urgente**' 100 }) '700: coleta nova urgente'
    Igual (& $modulo { Format-TextoCurto 'abcdefghij' 6 }) 'abcde…'
}

Teste 'Format-Duracao em minutos, horas e dias' {
    Igual (& $modulo { Format-Duracao 45 }) '45 min'
    Igual (& $modulo { Format-Duracao 125 }) '2 h'
    Igual (& $modulo { Format-Duracao 3000 }) '2 d'
}

# --- comandos (sem efeito) ----------------------------------------------------------------------------------

Teste 'tl nova -SoMostrar mostra o plano e não cria pasta nem ramo' {
    $saida = (tl nova Plataforma 'teste do painel zz' -Modelo opus -SoMostrar 6>&1 | Out-String)
    Contem $saida 'Plataforma · teste do painel zz'
    Contem $saida 'analise-acoes-plataforma-teste-do-painel-zz'
    Contem $saida 'feat/teste-do-painel-zz'
    Contem $saida '--model opus'
    Contem $saida 'só mostrando'
    $pasta = & $modulo { Join-Path (Get-PastaDasCopias) 'analise-acoes-plataforma-teste-do-painel-zz' }
    if (Test-Path -LiteralPath $pasta) { throw "criou a pasta $pasta" }
    $raiz = & $modulo { $script:RaizDoRepositorio }
    Igual @(& git -C $raiz branch --list 'feat/teste-do-painel-zz').Count 0
}

Teste 'tl nova recusa modelo e permissão desconhecidos e exige mesa e tarefa' {
    Contem (Erro { New-TlConversa Dados 'x' -Modelo gpt -SoMostrar }) 'Modelo desconhecido'
    Contem (Erro { New-TlConversa Dados 'x' -Permissao bypassPermissions -SoMostrar }) 'Modo de permissão desconhecido'
    Contem (Erro { New-TlConversa -SoMostrar }) 'Uso: tl nova'
}

Teste 'tl com comando desconhecido avisa e mostra a ajuda' {
    $saida = (tl xyz 6>&1 | Out-String)
    Contem $saida "Não conheço 'tl xyz'"
    Contem $saida 'tl nova'
    Contem $saida 'Satélites'
}

# --- instalador ---------------------------------------------------------------------------------------------

$instalador = (Resolve-Path (Join-Path $pastaDosTestes '../instalar.ps1')).Path
$pontePwsh = (Resolve-Path (Join-Path $pastaDosTestes '../ponte-pwsh.ps1')).Path
$ponteWindowsPowerShell = (Resolve-Path (Join-Path $pastaDosTestes '../ponte-windows-powershell.ps1')).Path
$pwsh = (Get-Process -Id $PID).Path

function Instalar([string]$Perfil, [string]$PerfilAntigo, [string[]]$Mais = @()) {
    <# Roda o instalador num pwsh filho, sempre com os dois perfis de teste: assim ele não toca os perfis de verdade
       nem reimporta o módulo desta suíte. #>
    & $pwsh -NoProfile -NonInteractive -File $instalador -Perfil $Perfil -PerfilAntigo $PerfilAntigo @Mais 2>&1 | Out-String
}

function PerfilDeTeste([string]$Nome) {
    $caminho = Join-Path ([IO.Path]::GetTempPath()) "tl-teste-$Nome-$PID.ps1"
    Remove-Item -LiteralPath $caminho -ErrorAction SilentlyContinue
    return $caminho
}

Teste 'instalar.ps1 escreve uma linha em cada perfil dado, avisa das janelas já abertas e não repete as linhas' {
    $perfil = PerfilDeTeste 'perfil'
    $perfilAntigo = PerfilDeTeste 'perfil-antigo'
    try {
        $saida = Instalar $perfil $perfilAntigo
        Contem $saida 'acrescentei: Import-Module'
        Contem $saida 'acrescentei: . '
        Contem $saida 'abertas'
        Contem $saida 'PowerShell 7'
        Contem $saida 'Windows PowerShell 5.1'
        $linhas = @(Get-Content -LiteralPath $perfil -Encoding utf8)
        Igual $linhas.Count 1
        Contem $linhas[0] 'TickerLab.psd1'
        $linhasAntigas = @(Get-Content -LiteralPath $perfilAntigo -Encoding utf8)
        Igual $linhasAntigas.Count 1
        Contem $linhasAntigas[0] 'ponte-windows-powershell.ps1'
        $deNovo = Instalar $perfil $perfilAntigo
        Contem $deNovo 'nada a fazer'
        NaoContem $deNovo 'acrescentei'
        Igual @(Get-Content -LiteralPath $perfil -Encoding utf8).Count 1
        Igual @(Get-Content -LiteralPath $perfilAntigo -Encoding utf8).Count 1
    } finally { Remove-Item -LiteralPath $perfil, $perfilAntigo -ErrorAction SilentlyContinue }
}

Teste 'instalar.ps1 deixa o tl pronto na própria janela; com -SoMostrar não toca perfil nenhum' {
    $perfil = PerfilDeTeste 'mostrar'
    $perfilAntigo = PerfilDeTeste 'mostrar-antigo'
    try {
        $saida = Instalar $perfil $perfilAntigo @('-SoMostrar')
        Contem $saida 'acrescentaria'
        Contem $saida 'nada mudou'
        foreach ($arquivo in $perfil, $perfilAntigo) {
            if (Test-Path -LiteralPath $arquivo) { throw "criou $arquivo só mostrando" }
        }
        $temTl = & $pwsh -NoProfile -NonInteractive -Command "& '$instalador' -Perfil '$perfil' -PerfilAntigo '$perfilAntigo' 6>&1 | Out-Null; [bool](Get-Command tl -ErrorAction SilentlyContinue)"
        Igual $temTl 'True'
    } finally { Remove-Item -LiteralPath $perfil, $perfilAntigo -ErrorAction SilentlyContinue }
}

# --- ponte para o Windows PowerShell 5.1 --------------------------------------------------------------------

Teste 'ponte-pwsh.ps1 importa o módulo e roda o tl com os argumentos recebidos' {
    $saida = & $pwsh -NoProfile -NonInteractive -File $pontePwsh xyz 2>&1 | Out-String
    Contem $saida "'tl xyz'"
    Contem $saida 'tl nova'
}

Teste 'ponte-windows-powershell.ps1 define um tl que repassa o comando a um pwsh' {
    $saida = & $pwsh -NoProfile -NonInteractive -Command ". '$ponteWindowsPowerShell'; tl xyz" 2>&1 | Out-String
    Contem $saida "'tl xyz'"
    Contem $saida 'tl nova'
}

$powershellAntigo = Get-Command powershell.exe -ErrorAction SilentlyContinue
if ($powershellAntigo) {
    Teste 'a ponte funciona a partir do Windows PowerShell 5.1 de verdade' {
        $saida = & $powershellAntigo.Source -NoProfile -NonInteractive -Command ". '$ponteWindowsPowerShell'; tl xyz" 2>&1 | Out-String
        Contem $saida "'tl xyz'"
        Contem $saida 'tl nova'
    }
} else {
    Write-Host '  (sem Windows PowerShell 5.1 neste sistema: a ponte a partir dele não foi testada aqui)'
}

Write-Host ''
if ($script:Falhas.Count -gt 0) {
    Write-Host ("{0} passaram, {1} falharam: {2}" -f $script:Passaram, $script:Falhas.Count, ($script:Falhas -join '; ')) -ForegroundColor Red
    exit 1
}
Write-Host ("Todos os {0} testes do painel passaram." -f $script:Passaram) -ForegroundColor Green
exit 0
