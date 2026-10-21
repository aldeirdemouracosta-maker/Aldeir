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

## 4. Módulo de áudio (efeitos e memes curtos)

- **Efeitos**: sintetizados proceduralmente em C++ (`core/src/audio.cpp`), determinísticos e testados (espectrogramas conferidos:
  laser desce, riser sobe, etc.). Não há áudio de terceiros embutido no app.
- **Memes**: o usuário **importa o próprio clipe** (seletor de arquivos do sistema, sem permissão de armazenamento). O app decodifica
  qualquer áudio/vídeo (`MediaExtractor` + `MediaCodec`), corta em 8 s, converte para mono 44,1 kHz, normaliza e aplica fade.
  Direitos autorais do clipe são de quem importa: áudio com copyright pode ser silenciado ou bloqueado pelo TikTok.
- **Voz**: `AudioRecord` (permissão de microfone já pedida na abertura, nunca de novo); grava assistindo ao vídeo, sem tocar os efeitos
  (para o microfone não captar o alto-falante).
- **Mixagem**: `AudioEngine` soma os eventos com ganho individual e um limitador suave (`tanh`), nunca estoura. A mesma mixagem alimenta a
  prévia (`AudioTrack`) e o MP4 (AAC-LC 128 kbps, muxer com duas trilhas, amostras intercaladas).
- **Robustez**: nomes validados (sem `../`), arquivos ausentes são ignorados, WAV truncado/inválido é recusado, eventos órfãos e
  `.part` limpos na abertura, exportação usa uma **cópia** dos eventos (editar durante a exportação não corrompe o vídeo).
- **Limites**: 400 sons por projeto, 30 s de voz, 8 s por meme. A narração fica sincronizada ao início do vídeo; sons que passam do
  fim do vídeo são cortados na exportação.

## 5. Troca de rosto (face swap)

Implementada como **módulo opcional** (APK `faceswap`), porque a detecção de pontos do rosto exige a biblioteca MediaPipe, que o proxy
do ambiente de desenvolvimento bloqueia. O GitHub Actions baixa a biblioteca (`-PfaceSwap=true`) e o modelo (`tools/fetch_face_model.sh`).

**Como funciona** (tudo no aparelho): extrai quadros do vídeo no ritmo do projeto (≤ 8 s, recorte 9:16) → MediaPipe devolve 478 pontos por
quadro (modo vídeo, rastreando) → filtro One-Euro tira o tremor → o rosto da foto é deformado triângulo a triângulo (Delaunay) sobre os
pontos do quadro → a cor é igualada (média/desvio) → máscara com borda suave pela distância ao contorno → quadro gravado no projeto.
A expressão (boca, olhos) acompanha o vídeo porque a malha da foto é deformada para a malha do quadro.

**Como foi validado**
- Núcleo C++ (`core/src/face_swap.cpp`) com testes sintéticos sob ASan/UBSan: geometria exata do mapeamento, cobertura da triangulação, correção
  de cor, bordas suaves, rosto cortado pelo canto, entradas inválidas.
- **Com dados reais**: modelo oficial + MediaPipe para Python numa imagem de teste de domínio público: os índices que o app usa batem com as listas
  oficiais (`tools/check_face_indices.py`); a troca "sobre si mesma" reproduz o alvo (diferença média 1,1/765) e uma foto espelhada entra na pose
  girada do alvo com olhos, boca e borda alinhados. Custo ≈ 60 ms/quadro de composição no PC.
- Os nomes da API Java do MediaPipe (`FaceLandmarker`, `detectForVideo`, `BaseOptions`...) foram conferidos no código-fonte oficial
  (`google-ai-edge/mediapipe`). **Ainda não executado no celular**, e a versão `0.10.14` do artefato Maven não foi verificada daqui.

**Limites honestos**: é troca por malha, não IA generativa: o rosto fica um pouco "colado" (sem refazer luz, barba, cabelo ou oclusões como
mão na frente do rosto), um rosto por vez, funciona melhor com foto frontal nítida e vídeo com rosto bem visível.

**Salvaguardas** (não substituem bom senso nem a lei): consentimento a cada troca (a foto é sua ou autorizada, o vídeo é usável, sem enganar,
difamar ou assediar); selo **CONTEÚDO ALTERADO • IA** em toda exportação que contenha quadros trocados, sem opção de desligar (apagar os quadros
trocados da linha do tempo remove o selo); nada sai do aparelho; o app não embute cenas de filmes nem fotos de ninguém. Um vídeo exportado ainda
pode ser recortado por quem quiser remover o selo: o app não consegue impedir isso. Direitos autorais do clipe e uso da imagem da pessoa
continuam sendo de responsabilidade de quem usa; evite publicar cenas de filmes sem autorização.
