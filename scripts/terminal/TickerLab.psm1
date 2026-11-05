#Requires -Version 7.0
# Painel do TickerLab no terminal (comando `tl`). Este arquivo só carrega as funções: cada arquivo de
# Privado/ (regras e leitores, com teste) e de Publico/ (um comando por arquivo) define as suas.

$script:PastaDoModulo = $PSScriptRoot
# O módulo mora em scripts/terminal/, então a raiz do repositório fica dois níveis acima.
$script:RaizDoRepositorio = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path

foreach ($pasta in 'Privado', 'Publico') {
    foreach ($arquivo in Get-ChildItem -Path (Join-Path $PSScriptRoot $pasta) -Filter *.ps1 | Sort-Object Name) {
        . $arquivo.FullName
    }
}

Export-ModuleMember -Function tl, Show-TlPainel, New-TlConversa, Show-TlFila, Show-TlPullRequests,
    Get-TlCopiasMescladas, Remove-TlCopiasMescladas, Start-TlCelular, Show-TlAjuda
