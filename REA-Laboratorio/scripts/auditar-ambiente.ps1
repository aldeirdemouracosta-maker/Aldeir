# REA-Laboratorio OS - Fase 0 - auditoria SOMENTE LEITURA (Windows PowerShell)
# Nao instala, nao altera, nao apaga. Unica escrita: um NOVO relatorio em relatorios\.
# Uso (na raiz C:\Projetos\REA-Laboratorio):  powershell -ExecutionPolicy Bypass -File scripts\auditar-ambiente.ps1
$ErrorActionPreference = 'Continue'
$raiz = (Get-Location).Path
$saida = Join-Path $raiz ("relatorios\AUDITORIA-LOCAL-{0}.md" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force (Split-Path $saida) | Out-Null
$L = New-Object System.Collections.Generic.List[string]
function Add($t) { $script:L.Add($t) }
function Tentar($nome, [scriptblock]$cmd) {
    Add "### $nome"; Add '```'
    try { $r = & $cmd 2>&1 | Out-String; Add ($r.Trim()) } catch { Add "NAO DISPONIVEL: $($_.Exception.Message)" }
    Add '```'
}
Add "# Auditoria local - $(Get-Date -Format s)"; Add "Raiz: $raiz"; Add ""
Add "## Conteudo do projeto (2 niveis, sem .git/node_modules)"; Add '```'
Get-ChildItem $raiz -Recurse -Depth 2 -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\(\.git|node_modules)(\\|$)' } |
  ForEach-Object { $_.FullName.Substring($raiz.Length) + $(if ($_.PSIsContainer) {'\'} else {"  ($($_.Length) B)"}) } | ForEach-Object { Add $_ }
Add '```'; Add ""
Add "## Ferramentas"
Tentar 'Git'       { git --version; git -C $raiz status -sb; git -C $raiz remote -v }
Tentar 'Node.js'   { node --version }
Tentar 'Python'    { python --version }
Tentar 'Java'      { java -version }
Tentar 'WSL2'      { wsl --status; wsl -l -v }
Tentar 'QEMU'      { qemu-system-x86_64 --version }
Tentar 'Codex'     { codex --version }
Tentar 'REA (MCP, somente leitura)' { codex mcp get rea }
Add "### Ghidra (busca somente leitura)"; Add '```'
$cands = @($env:GHIDRA_INSTALL_DIR) + (Get-ChildItem 'C:\','C:\Tools','C:\Program Files' -Directory -Filter 'ghidra*' -ErrorAction SilentlyContinue | ForEach-Object FullName)
$achou = $cands | Where-Object { $_ -and (Test-Path (Join-Path $_ 'ghidraRun.bat')) }
if ($achou) { $achou | ForEach-Object { Add "encontrado: $_" } } else { Add 'nao encontrado' }
Add '```'
Add "## Scripts e documentos de fases anteriores (candidatos)"; Add '```'
Get-ChildItem $raiz -Recurse -Include *.ps1,*.py,*.js,*.cmd,*.bat,*.md,*.json -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\(\.git|node_modules)\\' } | Select-Object -First 200 |
  ForEach-Object { Add ($_.FullName.Substring($raiz.Length) + "  " + $_.LastWriteTime.ToString('s')) }
Add '```'
$L | Set-Content -Encoding UTF8 $saida
Write-Host "Relatorio criado: $saida"
