# Análise de ferramentas e ajustes do porte

## 1. O que saiu do VectorMotion OS (excesso)

O zip original é um sistema operacional embarcado. Ficou de fora, por não existir ou não fazer sentido no Android:
boot BIOS/UEFI, slots A/B + dm-verity + RAUC, Recovery, ClamAV/YARA/USBGuard/AppArmor/nftables, Buildroot,
DRM/KMS, DMA-BUF/fences, evdev, V4L2/libcamera, ALSA, perfis RX580/P100, monitor de hardware.
Reaproveitado (reescrito, sem `std::filesystem`/`flock`/`statvfs`): modelo de timeline e gravação atômica
(tmp + fsync + rename), validação de entrada, conversão de cor e efeitos.

## 2. Bugs e riscos corrigidos no porte

| Ponto | Original | Agora |
|---|---|---|
| Armazenamento de frames | PPM sem compressão (≈ 6 MB por frame 1080×1920) | JPEG q92 (bem menor; depende da cena) |
| Frame duplicado + apagar | (recurso novo) | contagem de referências: o arquivo só é apagado se nenhuma cópia o usa |
| Nome de arquivo no manifesto | caminhos absolutos | só nomes simples; `../`, espaços e `\n` são rejeitados (testado) |
| `timeline` corrompida | (recurso novo) | reconstrói a partir dos JPEGs em vez de descartar o trabalho |
| Queda no meio da captura | (recurso novo) | `.part` e frames órfãos limpos na abertura |
| Conversão YUV | (recurso novo) | recusa planos pequenos demais (não estoura memória); strides arbitrários; dimensões ímpares |
| Exposição automática | (recurso novo) | trava de AE/AWB (frames não "piscam") |
| Concorrência | (recurso novo) | captura grava em outra thread; reprodução/exportação usam **cópia** da timeline |
| Espaço em disco | reserva de 256 MB | reserva de 150 MB antes de cada captura |

Validação: 100% do núcleo C++ testado com ASan/UBSan; a conversão RGBA→YUV foi comparada com o decodificador do
FFmpeg (BT.709, faixa limitada): diferença máxima de 3/255. O código Java compila contra o `android.jar` do
Android 10 (garante que nenhuma API acima da 29 foi usada). **Ainda não foi executado em aparelho** (sem
SDK/emulador no ambiente): o primeiro teste real é o APK do GitHub Actions.

## 3. Ferramentas complementares

Pesquisa feita em 21/10/2026 (resultados de busca; não verifiquei código-fonte de cada projeto):

- **Stop Motion Studio** (iOS/Android/desktop): é o app de referência, mas **proprietário** — não há fork possível.
- Não encontrei **nenhum app de stop-motion nativo de código aberto** para iOS/Android. O mais próximo é
  [szager/stop-motion](https://github.com/szager/stop-motion), que roda no navegador com webcam.
  Conclusão: "fork de app do iPhone" não é um caminho viável; por isso o app foi feito do zero em cima do núcleo existente.
- **FFmpegKit** foi [aposentado e removido do Maven Central](https://cdn.jsdelivr.net/gh/arthenica/ffmpeg-kit@main/README.md);
  forks comunitários existem, mas não verifiquei a manutenção deles. **Evitado**: a exportação usa `MediaCodec` + `MediaMuxer`
  do próprio Android (zero dependências, APK menor).
- **TikTok**: o envio usa `ACTION_SEND` com `video/mp4` para os pacotes `com.zhiliaoapp.musically` / `com.ss.android.ugc.trill`,
  com seletor genérico de reserva. Não usa o SDK de compartilhamento oficial (exige cadastro e chave).
- **Candidatos para depois**: Oboe (áudio de baixa latência), ThorVG (SVG/Lottie vetorial, já usado no original),
  Media3 Transformer (cortes/transições, se um dia a exportação ficar complexa).

## 4. Troca de rosto ("faceup")

Pedido novo, ainda **não implementado**. Plano e condições:

1. Detecção de pontos faciais **no aparelho** com o [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/android)
   (`com.google.mediapipe:tasks-vision`; 3D landmarks + blendshapes). Licença do código e dos modelos **a confirmar** antes de embarcar.
2. Troca por warp de malha (triângulos) + correção de cor, em C++ no mesmo núcleo.
3. Regras de produto: o rosto de origem precisa ser do próprio usuário ou ter consentimento; todo vídeo com troca recebe
   marca d'água visível "conteúdo alterado" (não removível no app). Nada sai do aparelho.
4. Custo: modelo ≈ alguns MB e um AAR (primeira dependência de terceiros do app).

Pergunta em aberto: "faceup" é o nome de um app específico que você quer imitar, ou o recurso genérico de trocar/animar rosto?
