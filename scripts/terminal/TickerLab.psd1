@{
    RootModule        = 'TickerLab.psm1'
    ModuleVersion     = '0.1.0'
    GUID              = '959eff54-714c-4e35-9016-ce6dffb05da3'
    Author            = 'TickerLab'
    Description       = 'Painel do TickerLab no terminal: abre e acompanha as conversas do Claude Code (comando tl).'
    PowerShellVersion = '7.0'
    FunctionsToExport = @(
        'tl',
        'Show-TlPainel',
        'New-TlConversa',
        'Show-TlFila',
        'Show-TlPullRequests',
        'Get-TlCopiasMescladas',
        'Remove-TlCopiasMescladas',
        'Start-TlCelular',
        'Show-TlAjuda'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
