# Instala o proxy de correção da Fábrica no Windows (não precisa de administrador).
# Uso mais simples: dê dois cliques em instalar-windows.cmd
# Opções (PowerShell):
#   .\instalar-windows.ps1 -Servidor http://127.0.0.1:1234   # LM Studio (RX 580 via Vulkan)
#   .\instalar-windows.ps1 -Servidor http://127.0.0.1:11434  # Ollama
#   .\instalar-windows.ps1 -Modelo qwen/qwen3-8b -SemPensar
param(
  [string]$Servidor = "",
  [string]$Modelo = "",
  [switch]$SemPensar,
  [int]$Porta = 11435
)
$ErrorActionPreference = "Stop"
$Origem = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pasta = Join-Path $env:LOCALAPPDATA "fabrica-correcoes"
$Log = Join-Path $Pasta "proxy.log"
$Atalho = Join-Path ([Environment]::GetFolderPath("Startup")) "Fabrica Proxy.lnk"

function Info($m) { Write-Host "->  $m" }
function Ok($m) { Write-Host "OK  $m" -ForegroundColor Green }
function Falha($m) { Write-Host "ERRO  $m" -ForegroundColor Red; exit 1 }
function Modelos($url) {
  try { return Invoke-RestMethod -Uri "$url/v1/models" -TimeoutSec 3 } catch { return $null }
}
function PortaAberta($p) {
  $tcp = New-Object System.Net.Sockets.TcpClient
  try { $tcp.Connect("127.0.0.1", $p); return $true } catch { return $false } finally { $tcp.Close() }
}

# --- Python
$py = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { Falha "Python não encontrado. Instale em python.org marcando 'Add python.exe to PATH'." }
$versao = & $py.Source --version 2>&1
if ($LASTEXITCODE -ne 0 -or "$versao" -notmatch "Python 3") {
  Falha "O 'python' do PATH não funciona ($versao). Instale o Python em python.org."
}
$pyw = Join-Path (Split-Path $py.Source) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py.Source }
Info "Usando $versao"

if (-not (Test-Path (Join-Path $Origem "fabrica_proxy.py"))) { Falha "fabrica_proxy.py não está ao lado deste script." }
& $py.Source -m py_compile (Join-Path $Origem "fabrica_proxy.py")
if ($LASTEXITCODE -ne 0) { Falha "fabrica_proxy.py tem erro de sintaxe." }

# --- servidor de IA: LM Studio (1234) ou Ollama (11434)
if (-not $Servidor) {
  foreach ($u in @("http://127.0.0.1:1234", "http://127.0.0.1:11434")) {
    if (Modelos $u) { $Servidor = $u; break }
  }
  if (-not $Servidor) {
    $Servidor = "http://127.0.0.1:11434"
    Write-Warning "Nem o LM Studio (1234) nem o Ollama (11434) responderam. Vou usar $Servidor; ligue o servidor depois."
  }
}
Info "Servidor de IA: $Servidor"
if (-not $Modelo) {
  $lista = Modelos $Servidor
  if ($lista -and $lista.data) {
    $q = $lista.data | Where-Object { $_.id -match "qwen3" } | Select-Object -First 1
    if ($q) { $Modelo = $q.id }
  }
  if (-not $Modelo) { $Modelo = "qwen3:8b" }
}
Info "Modelo padrão: $Modelo"

# --- para um proxy antigo que esteja rodando
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*fabrica_proxy.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# --- copia os arquivos
Info "Copiando para $Pasta"
New-Item -ItemType Directory -Force -Path $Pasta | Out-Null
Copy-Item (Join-Path $Origem "fabrica_proxy.py") $Pasta -Force
Copy-Item (Join-Path $Origem "desinstalar-windows.ps1") $Pasta -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Origem "desinstalar-windows.cmd") $Pasta -Force -ErrorAction SilentlyContinue

# --- comando fabrica-segura
$wrapper = @'
# Fábrica passando pelo proxy de correção.
$a = @($args)
$real = Get-Command fabrica -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $real) { Write-Host "Comando 'fabrica' não encontrado no PATH." -ForegroundColor Red; exit 1 }
$tcp = New-Object System.Net.Sockets.TcpClient
try { $tcp.Connect("127.0.0.1", __PORTA__) } catch { Write-Warning "O proxy não está rodando. Reinicie o Windows ou rode o instalador de novo." } finally { $tcp.Close() }
$extra = @()
if (-not (($a -contains "--nuvem") -or ($a -contains "--claude"))) {
  if (-not ($a | Where-Object { $_ -eq "--url" -or $_ -like "--url=*" })) { $extra += @("--url", "http://127.0.0.1:__PORTA__/v1") }
  if (-not ($a | Where-Object { $_ -eq "-m" -or $_ -eq "--modelo" -or $_ -like "--modelo=*" -or $_ -eq "modelos" })) {
    $m = $env:FABRICA_MODELO
    if (-not $m) { $m = "__MODELO__" }
    $extra += @("-m", $m)
  }
}
& $real.Source @a @extra
exit $LASTEXITCODE
'@
$wrapper = $wrapper.Replace("__PORTA__", "$Porta").Replace("__MODELO__", $Modelo)
$utf8bom = New-Object System.Text.UTF8Encoding $true
[IO.File]::WriteAllText((Join-Path $Pasta "fabrica-segura.ps1"), $wrapper, $utf8bom)
[IO.File]::WriteAllText((Join-Path $Pasta "fabrica-segura.cmd"),
  "@powershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0fabrica-segura.ps1`" %*`r`n",
  (New-Object System.Text.ASCIIEncoding))

# --- PATH do usuário
$path = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $path) { $path = "" }
if (($path -split ";") -notcontains $Pasta) {
  [Environment]::SetEnvironmentVariable("Path", ($path.TrimEnd(";") + ";" + $Pasta).TrimStart(";"), "User")
  Info "Pasta adicionada ao PATH (vale para janelas novas do terminal)"
}

# --- inicia com o Windows (atalho na pasta Inicializar) e já liga agora
$argumentos = "`"$Pasta\fabrica_proxy.py`" --porta $Porta --ollama $Servidor --log `"$Log`""
if ($SemPensar) { $argumentos += " --sem-pensar" }
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut($Atalho)
$lnk.TargetPath = $pyw
$lnk.Arguments = $argumentos
$lnk.WorkingDirectory = $Pasta
$lnk.WindowStyle = 7
$lnk.Description = "Proxy de correção da Fábrica"
$lnk.Save()
Start-Process -FilePath $pyw -ArgumentList $argumentos -WorkingDirectory $Pasta -WindowStyle Hidden
Start-Sleep -Seconds 2
if (PortaAberta $Porta) { Ok "Proxy rodando na porta $Porta e configurado para iniciar com o Windows" }
else { Falha "O proxy não subiu. Veja o log: $Log" }

Write-Host ""
Write-Host "Pronto. Abra um terminal NOVO, entre na pasta do projeto e use:  fabrica-segura"
Write-Host "  Outro modelo:      `$env:FABRICA_MODELO='qwen2.5:7b'; fabrica-segura"
Write-Host "  Ver as correções:  Get-Content `"$Log`" -Wait"
Write-Host "  Desinstalar:       $Pasta\desinstalar-windows.cmd"
