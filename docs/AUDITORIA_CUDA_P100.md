# Auditoria CUDA P100
Consultas em 19 e 20/10/2026, PowerShell Windows. Somente leitura; drivers inalterados.
Windows 10 Enterprise 10.0.19045 x64; Xeon E5-2630L v2, 6 nucleos/12 threads.
RAM visivel 33484200 KiB; livre 18002680 KiB na primeira coleta (valor transitorio).
Discos: C total 510993108992/livre 308295454720 bytes; D 1000187359232/999957004288; E 1000202039296/245742018560.
GPUs enumeradas: AMD Radeon RX 580 2048SP (driver 31.0.21925.1001) e NVIDIA GeForce 210 (driver 341.74).
P100 NAO detectada. VRAM P100, compute 6.0, alimentacao, refrigeracao e limites de potencia: nao verificaveis nesta maquina. Inspecao fisica continua pendente.
NVIDIA-SMI 341.74: GeForce 210 WDDM; 972/979 MiB; 43 C; fan 100%; potencia N/A. Esses dados NAO descrevem uma P100.
GPU AMD adicional enumerada; conexao fisica do monitor nao inspecionada.
Python 3.12.10; pip 25.0.1; Go go1.27.2 windows/amd64; Git 2.56.0.windows.2.
nvcc, ffmpeg e ffprobe nao encontrados no PATH; nao prova ausencia em todo o disco. Diretorio padrao do CUDA Toolkit nao encontrado.
nvcuda.dll presente em System32; presenca nao comprova runtime moderno funcional.
nvidia-smi fora do PATH, localizado em C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe.
FFmpeg/NVENC/NVDEC/filtros: nao testados, nenhum encoder validado.

## Comandos executados
- Get-Location; Get-ChildItem -Force
- Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,TotalVisibleMemorySize,FreePhysicalMemory
- Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
- Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM
- Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,PNPDeviceID
- Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID,Size,FreeSpace
- Get-PSDrive -PSProvider FileSystem
- Get-Command nvidia-smi,nvcc,go,python,python3,ffmpeg,ffprobe,git -ErrorAction SilentlyContinue
- go version; python --version; python -m pip --version; git --version
- python -c "import importlib.util; print(importlib.util.find_spec('torch'))"
- Get-Item nos caminhos padrao de nvcuda.dll, nvidia-smi.exe e CUDA Toolkit
- & 'C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe'
Consultas CIM inicialmente falharam com acesso negado no sandbox; repetidas com autorizacao fora dele e bem-sucedidas.
Criterio da fase 0: NAO APROVADO, sem P100 detectada e sem operacao CUDA real aprovada.
