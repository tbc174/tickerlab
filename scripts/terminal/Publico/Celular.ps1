# `tl celular`: Remote Control do Claude Code, para comandar este PC pelo app do celular ou pelo claude.ai/code.

function Start-TlCelular {
    <# Roda `claude remote-control` na raiz do repositório (ou na pasta dada). O PC fica ligado e acordado:
       a conversa roda aqui; o celular só comanda. Ctrl+C encerra. #>
    param([string]$Pasta = $script:RaizDoRepositorio)
    if (-not (Test-Ferramenta 'claude')) {
        Write-Aviso 'claude não está no PATH: não dá para ligar o Remote Control.'
        return
    }
    Write-Aviso 'Deixe o PC ligado e acordado: a conversa roda aqui e o celular só comanda. Ctrl+C encerra.'
    Push-Location -LiteralPath $Pasta
    try { & claude remote-control } finally { Pop-Location }
}
