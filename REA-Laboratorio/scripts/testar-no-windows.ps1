# REA-Laboratorio OS - teste do nucleo Go no Windows. NAO instala nada e NAO altera C:\Projetos\REA-Laboratorio.
# Uso: powershell -ExecutionPolicy Bypass -File testar-no-windows.ps1
$ErrorActionPreference = 'Stop'
foreach ($c in 'git','go') { if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { Write-Host "FALTA: $c (instale por conta propria e rode de novo)"; exit 1 } }
$dest = Join-Path $env:USERPROFILE 'rea-teste'
if (-not (Test-Path $dest)) {
  git clone --branch claude/festive-dirac-kpg3o1 --single-branch https://github.com/aldeirdemouracosta-maker/Aldeir.git $dest
} else { git -C $dest pull --ff-only origin claude/festive-dirac-kpg3o1 }
Set-Location (Join-Path $dest 'REA-Laboratorio\core')
go vet ./...            ; if ($LASTEXITCODE) { exit 1 }
go test ./... 2>&1 | Tee-Object -FilePath ..\relatorio-go-test.txt
go build -trimpath -ldflags="-s -w" -o rea.exe .\cmd\rea ; if ($LASTEXITCODE) { exit 1 }
$out = Join-Path (Get-Location) 'resultado-teste.txt'
& { '== modulos'; .\rea.exe modulos; '== ferramentas'; .\rea.exe ferramentas; '== ia'; .\rea.exe ia
    '== hash'; .\rea.exe hash .\rea.exe; '== detectar'; .\rea.exe detectar .\rea.exe
    '== analisar'; .\rea.exe analisar --saida .\rea-saida --autorizado-por $env:USERNAME --origem 'build local' .\rea.exe
    '== guardian (deve falhar)'; .\rea.exe analisar --saida .\rea-saida C:\Windows } 2>&1 | Tee-Object -FilePath $out
Write-Host "`nPronto. Envie o conteudo de: $out e ..\relatorio-go-test.txt"
