# HRAIL - coletor SOMENTE LEITURA para Windows (substitui coletar-na-maquina.sh).
# Nao exige administrador, nao altera o sistema, nao coleta nome do PC, usuario nem numeros de serie.
# Uso (a politica de execucao muda apenas para ESTE processo):
#   powershell -ExecutionPolicy Bypass -File scripts\coletar-windows.ps1
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $PSScriptRoot
$saida = Join-Path $raiz 'reports'
New-Item -ItemType Directory -Force -Path $saida | Out-Null

function Seguro($bloco) { try { & $bloco } catch { $null } }

# Recursos de CPU via API do Windows (funciona no PowerShell 5.1)
Add-Type -Namespace Hrail -Name K32 -MemberDefinition '[DllImport("kernel32.dll")] public static extern bool IsProcessorFeaturePresent(uint f);'
$feat = @{ sse2 = 10; sse3 = 13; ssse3 = 36; sse4_1 = 37; sse4_2 = 38; avx = 39; avx2 = 40; avx512f = 41 }
$cpuFeatures = @{}
foreach ($k in $feat.Keys) { $cpuFeatures[$k] = Seguro { [Hrail.K32]::IsProcessorFeaturePresent([uint32]$feat[$k]) } }

$cpu = Seguro { Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors }
$gpus = Seguro {
    Get-CimInstance Win32_VideoController | ForEach-Object {
        $pnp = $_.PNPDeviceID
        [pscustomobject]@{
            name          = $_.Name
            pnp_device_id = $pnp
            vendor_id     = if ($pnp -match 'VEN_([0-9A-F]{4})') { '0x' + $Matches[1].ToLower() } else { $null }
            device_id     = if ($pnp -match 'DEV_([0-9A-F]{4})') { '0x' + $Matches[1].ToLower() } else { $null }
            revision      = if ($pnp -match 'REV_([0-9A-F]{2})') { '0x' + $Matches[1].ToLower() } else { $null }
            driver_version = $_.DriverVersion
            driver_date   = "$($_.DriverDate)"
            adapter_ram_bytes_wmi = $_.AdapterRAM   # ATENCAO: campo de 32 bits; satura em 4 GiB. Nao use como VRAM real.
        }
    }
}
$ram = Seguro { (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory }
$os = Seguro { Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture }
$discos = Seguro { Get-CimInstance Win32_DiskDrive | Select-Object Model, Size, MediaType }

# vulkaninfo, se existir (somente consulta)
$vk = $null
$vkExe = Get-Command vulkaninfo, vulkaninfoSDK -ErrorAction SilentlyContinue | Select-Object -First 1
if ($vkExe) { $vk = Seguro { & $vkExe.Source --summary 2>&1 | Out-String } }

$inv = [ordered]@{
    collected_at = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
    origin       = 'measured'
    collector    = 'coletar-windows.ps1 (Fase 1, formato diferente do inventario Linux)'
    os           = $os
    cpu          = $cpu
    cpu_features = $cpuFeatures
    ram_total_bytes = $ram
    storage      = $discos
    gpus         = $gpus
    vulkaninfo_summary = $vk
    notes        = @('Dados lidos por WMI/CIM e kernel32; nada foi alterado.',
                     'adapter_ram_bytes_wmi satura em 4 GiB: a VRAM real deve vir do vulkaninfo ou do driver.',
                     'Se vulkaninfo estiver ausente, a parte Vulkan fica nula (desconhecida, nao falsa).')
}
$arq = Join-Path $saida 'hardware_windows.json'
$inv | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 $arq
Write-Host "Pronto: $arq"
Write-Host 'Envie esse arquivo para analise. Ele nao contem nome do PC, usuario nem numeros de serie.'
