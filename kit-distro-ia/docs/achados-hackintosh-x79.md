# Achados: macOS (Hackintosh) em X79 + Xeon E5-2630L v2

Hardware: HUANANZHI X79 v3.1, Xeon E5-2630L v2, RX 580 2048SP. Descrições vêm dos repositórios; não são testes neste computador.

Aviso: a conversa original não trazia URLs de vários repositórios; nenhuma foi inventada. Onde está 'buscar', localize pelo termo.


## Projetos X79

- **Gabriel Luchina - base X79 Ivy Bridge-E**: Base OpenCore específica para X79 dessa geração. README informa atualização em 27/09/2026, OpenCore 1.0.8 e suporte até Monterey. Utilidade/limite: Melhor ponto de partida para estudar uma EFI própria. Link: buscar: GitHub Gabriel Luchina X79 Ivy Bridge-E OpenCore
- **OpenCore X79 - Xeon E5-2650 v2**: Configuração para X79, Xeon v2 e RX 470. Documentação curta, dois commits visíveis. Utilidade/limite: Exemplo próximo da geração do seu processador; manutenção atual não confirmada. Link: buscar: GitHub OpenCore X79 E5-2650 v2 RX 470
- **PlexHD X79 - igor7302**: Autor declara funcionamento com E5-2640 v1 e RX 570; configurações para Mojave, Catalina e Big Sur. Utilidade/limite: Referência para comparar correções de X79. Algumas tabelas são específicas do CPU do autor. Link: buscar: GitHub igor7302 PlexHD X79
- **Hackintosh X79m-s**: Mantém material OpenCore e marca a configuração Clover como legado sem manutenção. Utilidade/limite: Útil para estudar a migração de Clover para OpenCore. Link: buscar: GitHub Hackintosh X79m-s
- **Yaming Network - X79 no Gitee**: Histórico com ajustes de USB, sincronização do processador, energia e adaptações para macOS 13/14 sem AVX2. Utilidade/limite: Fonte chinesa relevante para investigar versões posteriores ao Monterey. Link: buscar: Gitee Yaming X79 黑苹果 OpenCore

## Projetos antigos

- **X79 E5-2696 v2 - Clover EFI**: X79, Xeon v2 e R9 Nano; documentação mínima. Abandono formal não confirmado. Utilidade/limite: Comparar uma EFI antiga da plataforma. Link: buscar: GitHub X79 E5-2696 v2 Clover EFI
- **X79/X99/X299 - andrescera**: README baseado em OpenCore 0.6.8, Catalina e Big Sur; conteúdo principalmente de X99. Utilidade/limite: Referências de ACPI, Uncore e energia; cuidado com diferenças entre gerações. Link: buscar: GitHub andrescera X79 X99 X299
- **Clover Bootloader**: Bootloader para macOS, Windows e Linux. Utilidade/limite: Interpretar configurações antigas e comparar com OpenCore. Link: https://github.com/CloverHackyColor/CloverBootloader

## RX 580 2048SP

- **ChinaDragonNB/HackApple**: Big Sur 11.6 com Sapphire RX 580 2048SP após gravar BIOS de RX 570. Hardware do autor: MSI B360M + i5-9400F. Utilidade/limite: Prova de funcionamento após modificação, mas não é solução universal; exige identificar fabricante, memória e BIOS da sua placa. Link: https://github.com/ChinaDragonNB/HackApple (caminho citado na pesquisa)

## Caminhos via Linux (VM)

- **OSX-KVM**: macOS em QEMU/KVM com OpenCore. Utilidade/limite: Validar requisitos da versão e da VM. Link: https://github.com/kholia/OSX-KVM
- **macOS-Simple-KVM**: Scripts para VM no Linux; High Sierra, Mojave e Catalina. Utilidade/limite: Voltado a versões antigas; manutenção não confirmada. Link: https://github.com/foxlet/macOS-Simple-KVM
- **Docker-OSX**: Automatiza VM macOS (QEMU/KVM) dentro de Docker. Utilidade/limite: Continua dependendo de virtualização; não elimina limites do hardware. Link: https://github.com/sickcodes/Docker-OSX

## Referências

- Dortania - OpenCore Install Guide: https://dortania.github.io/OpenCore-Install-Guide/
- Dortania - GPU Buyers Guide (compatibilidade da RX 580 2048SP): https://dortania.github.io/GPU-Buyers-Guide/
- CryptexFixup (instalar/atualizar Ventura sem AVX2): https://github.com/acidanthera/CryptexFixup
- InsanelyMac - relato Mojave em JingSha/Kllisre Dual X79 com 2x E5-2630L v2 (Clover): buscar em https://www.insanelymac.com: E5-2630L v2 X79 Mojave Clover

## Kernel
- XanMod LTS x64v2 (nunca x64v3: exige AVX2). LTS 6.18.53 e MAIN 7.2.7 em 21/09/2026.

- XanMod (site oficial): https://xanmod.org
- Instalação do XanMod no Debian 13/12 (LinuxCapable): https://www.linuxcapable.com/how-to-install-xanmod-kernel-on-debian-linux/
- XanMod 7.2.7 e LTS 6.18.53 (21/09/2026): https://www.linuxcompatible.org/story/xanmod-kernel-727-and-61853-now-available-for-debian-and-ubuntu/

## Limites
Codeberg bloqueado durante a pesquisa. Cobertura ampla, mas não exaustiva.
