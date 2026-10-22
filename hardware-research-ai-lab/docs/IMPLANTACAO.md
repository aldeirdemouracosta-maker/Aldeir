# Modelo de implantação: Go, Linux ou sistema no pen drive?

**O HRAIL é um programa Go para Linux, portátil, e não um sistema operacional.**

- **Go:** um único binário estático (`CGO_ENABLED=0`), sem dependências de execução. Banco, relatórios e configuração ficam ao lado dele (`--raiz`).
- **Linux:** a coleta lê `/proc` e `/sys` e (opcional) chama `vulkaninfo`. Em Windows/macOS não funciona.
- **Pen drive:** pode levar o pacote (`scripts/empacotar-usb.sh DESTINO`) e rodá-lo em qualquer Linux. Prefira ext4/exFAT; FAT32 limita arquivos a 4 GiB.

## Por que não um sistema próprio no pen drive
1. Medir a RX 580 exige o **driver real instalado** (amdgpu + Mesa RADV da máquina); um sistema à parte mediria outra pilha.
2. O laboratório não pode alterar kernel/driver/firmware; um SO próprio aumenta a superfície de risco sem ganho.
3. Manutenção: um SO inteiro seria trabalho desproporcional à pesquisa.

## Quando um Live USB faz sentido
Para rodar em máquina sem Linux instalado: inicie um Ubuntu Live (sem instalar), copie o pacote e execute `coletar-na-maquina.sh`.
Resultado: o Live já traz amdgpu/Mesa, então o diagnóstico é válido, e nada no disco interno é alterado. Sem persistência,
salve `reports/` em outro pen drive.

## Integração com o Peregrinus OS
Futura, por contrato JSON (`hardware inspect`, exportação do banco). O HRAIL permanece independente.

## Windows
O binário `hrail` e os scripts `.sh` **não funcionam no Windows** (a coleta depende de `/proc` e `/sys`).
Opções:
1. **Coletor PowerShell** (somente leitura, sem administrador): `powershell -ExecutionPolicy Bypass -File scripts\coletar-windows.ps1`
   gera `reports\hardware_windows.json` (CPU/AVX2, GPU com PCI ID e revisão, driver, RAM, discos, `vulkaninfo` se existir).
   Formato diferente do inventário Linux; serve para validar o perfil da RX 580 2048SP. **Não foi testado em Windows real** (sem PowerShell no ambiente de criação).
2. **Ubuntu Live no pen drive** (recomendado para o laboratório completo): inicia o Linux sem instalar, com amdgpu/Mesa, e roda o HRAIL de verdade.
3. WSL2 **não serve** para inspecionar a GPU: expõe uma GPU virtual (`/dev/dxg`), sem PCI/sysfs reais do amdgpu.
