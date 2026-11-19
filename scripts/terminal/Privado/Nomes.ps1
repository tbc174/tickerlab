# Nomes: mesas, cópias, ramos e títulos. Tudo deriva de "Mesa · tarefa" (ADR 0067), o nome que a conversa
# tem no app, no quadro de sessões e na fila.

$script:MESAS = [ordered]@{
    diretoria  = @{ Nome = 'Diretoria';  Emoji = '🧭'; Cor = '#5B8DEF' }
    dados      = @{ Nome = 'Dados';      Emoji = '🗄️'; Cor = '#3FA37A' }
    plataforma = @{ Nome = 'Plataforma'; Emoji = '🖥️'; Cor = '#8E6CD1' }
    produto    = @{ Nome = 'Produto';    Emoji = '🧩'; Cor = '#E08E3C' }
    marketing  = @{ Nome = 'Marketing';  Emoji = '📣'; Cor = '#D95D7A' }
    financeiro = @{ Nome = 'Financeiro'; Emoji = '💰'; Cor = '#C9A227' }
    satelites  = @{ Nome = 'Satélites';  Emoji = '🛰️'; Cor = '#6C8A99' }
}

# Palavras que não dizem nada sobre a tarefa; ficam fora da comparação entre nome de conversa e pasta.
$script:PALAVRAS_VAZIAS = @(
    'a', 'o', 'e', 'de', 'da', 'do', 'das', 'dos', 'em', 'no', 'na', 'nos', 'nas', 'por', 'para', 'com', 'sem',
    'que', 'os', 'as', 'um', 'uma', 'ao', 'aos'
)

function ConvertTo-NomeSimples([string]$Texto) {
    <# "Satélites · TCE-CE coleta" vira "satelites-tce-ce-coleta": sem acento, minúsculas, hífens. #>
    $semAcento = $Texto.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', ''
    ($semAcento.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
}

function Resolve-Mesa([string]$Mesa) {
    <# A mesa (Nome, Emoji, Cor, Chave) a partir de qualquer grafia; erro claro se não existe. #>
    $chave = ConvertTo-NomeSimples $Mesa
    if (-not $script:MESAS.Contains($chave)) {
        $nomes = ($script:MESAS.Values | ForEach-Object { $_.Nome }) -join ', '
        throw "Mesa desconhecida: '$Mesa'. As mesas são: $nomes."
    }
    $resolvida = $script:MESAS[$chave].Clone()
    $resolvida.Chave = $chave
    return $resolvida
}

function Get-NomeDaCopia([string]$Mesa, [string]$Tarefa) {
    <# Pasta da cópia do repositório: analise-acoes-<mesa>-<tarefa> (regra do CLAUDE.md). #>
    "$($script:PREFIXO_DA_COPIA)-$((Resolve-Mesa $Mesa).Chave)-$(ConvertTo-NomeSimples $Tarefa)"
}

function Get-TituloDaConversa([string]$Mesa, [string]$Tarefa) {
    <# Nome da conversa no formato do quadro de sessões: "Mesa · tarefa". #>
    "$((Resolve-Mesa $Mesa).Nome) · $Tarefa"
}

function Get-NomeDoRamo([string]$Tipo, [string]$Tarefa) {
    <# Ramo do Git no formato do AGENTS.md: feat/<tarefa>, fix/<tarefa>... #>
    if ($Tipo -notin $script:TIPOS_DE_RAMO) {
        throw "Tipo de ramo desconhecido: '$Tipo'. Use um de: $($script:TIPOS_DE_RAMO -join ', ')."
    }
    "$Tipo/$(ConvertTo-NomeSimples $Tarefa)"
}

function Get-MesaDoNome([string]$NomeDaConversa) {
    <# "Dados · TCE-CE (682)" dá "Dados"; $null quando o nome não segue o formato ou a mesa não existe. #>
    if ($NomeDaConversa -notmatch '^\s*([^·]+?)\s*·') { return $null }
    $chave = ConvertTo-NomeSimples $Matches[1]
    if ($script:MESAS.Contains($chave)) { return $script:MESAS[$chave].Nome }
    return $null
}

function Get-PalavrasDoNome([string]$Texto) {
    <# As palavras com significado de um nome ("dados-tce-ce-coleta" dá dados, tce, ce, coleta). #>
    @((ConvertTo-NomeSimples $Texto) -split '-' |
        Where-Object { $_.Length -ge 2 -and $_ -notin $script:PALAVRAS_VAZIAS } |
        Select-Object -Unique)
}

function Test-NomesParecidos([string]$NomeDaConversa, [string]$NomeDaCopia) {
    <# Diz se uma conversa aberta provavelmente usa a cópia: mesma mesa e ao menos uma palavra da tarefa em
       comum. É uma pista, não uma certeza: serve para `tl limpar` esperar em vez de apagar. #>
    $daConversa = Get-PalavrasDoNome $NomeDaConversa
    $sufixo = $NomeDaCopia -replace "^$([regex]::Escape($script:PREFIXO_DA_COPIA))-", ''
    $daCopia = Get-PalavrasDoNome $sufixo
    if ($daConversa.Count -eq 0 -or $daCopia.Count -eq 0) { return $false }
    $mesmaMesa = $daConversa[0] -eq $daCopia[0]
    $emComum = @($daCopia | Select-Object -Skip 1 | Where-Object { $_ -in $daConversa })
    return $mesmaMesa -and $emComum.Count -ge 1
}
