# Remove o proxy de correção da Fábrica do Windows. A Fábrica original não é tocada.
$Pasta = Join-Path $env:LOCALAPPDATA "fabrica-correcoes"
$Atalho = Join-Path ([Environment]::GetFolderPath("Startup")) "Fabrica Proxy.lnk"
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*fabrica_proxy.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-Item $Atalho -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "Atividade da Fabrica.url") -Force -ErrorAction SilentlyContinue
# devolve a configuração original do Fábrica App
foreach ($l in @($env:APPDATA, $env:LOCALAPPDATA, (Join-Path $HOME ".config")) | Where-Object { $_ -and (Test-Path $_) }) {
  Get-ChildItem -Path $l -Filter "configuracoes.json.antes-do-proxy" -Recurse -Depth 3 -File -ErrorAction SilentlyContinue |
    ForEach-Object {
      $orig = $_.FullName.Substring(0, $_.FullName.Length - ".antes-do-proxy".Length)
      Move-Item $_.FullName $orig -Force
      Write-Host "OK  Configuração restaurada: $orig" -ForegroundColor Green
    }
}
$path = [Environment]::GetEnvironmentVariable("Path", "User")
if ($path) {
  $novo = ($path -split ";" | Where-Object { $_ -and $_ -ne $Pasta }) -join ";"
  [Environment]::SetEnvironmentVariable("Path", $novo, "User")
}
Set-Location $env:USERPROFILE
Remove-Item $Pasta -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "OK  Proxy de correção removido. A Fábrica original continua instalada." -ForegroundColor Green
