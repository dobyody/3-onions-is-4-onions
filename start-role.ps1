param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet('transmitter', 'receiver', 'scope', 'demo')]
    [string]$Role,
    [switch]$Print
)

$ErrorActionPreference = 'Stop'
$roleFolders = @{
    transmitter = '01-transmitter'
    receiver = '02-receiver'
    scope = '03-scope'
    demo = '04-demo'
}
$rolePath = Join-Path $PSScriptRoot $roleFolders[$Role]
$prompt = Get-Content -Raw -LiteralPath (Join-Path $rolePath 'START.md')
if ($Print) {
    Write-Output $rolePath
    Write-Output $prompt
    return
}

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Codex CLI is unavailable. Open an agent session in the role folder and paste START.md.'
}

Push-Location -LiteralPath $rolePath
try {
    & codex $prompt
    if ($LASTEXITCODE -ne 0) {
        throw "Codex exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
