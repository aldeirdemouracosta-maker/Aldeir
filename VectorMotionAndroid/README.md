# Vector Motion — estúdio de stop-motion/CGI para Shorts e TikTok (Android 10)

Derivado do *VectorMotion OS v1.0-rc1* (C++ embarcado). Aqui só ficou o que faz sentido num celular:
o núcleo C++ portátil e um app Android nativo, **sem nenhuma dependência de terceiros** (nem AndroidX).

## O que já funciona (marco 1)

- Câmera traseira em **9:16** (Camera2), captura de frames em 1080×1920, **onion skin** ciano.
- **Trava de exposição/balanço de branco** (evita "piscar" entre frames).
- Linha do tempo: selecionar, mover, duplicar, apagar, segurar frame (×N), FPS 6–24, desfazer.
- **Efeitos CGI em C++**: Herói (teal & orange), Energia (brilho + aberração cromática), Cósmico, Noir (vermelho isolado), com intensidade.
- Reprodução em loop com os efeitos.
- **Exportação MP4** vertical H.264 30 fps → `Filmes/VectorMotion`, e botão **Enviar ao TikTok** (ou outros apps).
- **Som & Memes** (botão *Som*): 9 efeitos sintetizados em C++ (explosão, tiro, whoosh, laser, boom, vidro, buzina, riser, scratch),
  **importar meme** (áudio ou vídeo do seu aparelho, cortado em 8 s e normalizado), **gravar voz** assistindo ao vídeo, volume por som.
  Cada som entra no frame selecionado; a mixagem toca na reprodução e vai como trilha AAC no MP4 exportado.
- **Trocar rosto** (painel *CGI* → "Trocar rosto"): escolha um vídeo (até 8 s) e uma foto; o rosto da foto é colocado no rosto do vídeo
  e acompanha a cena (pontos do rosto → deformação da foto → correção de cor → borda suave, com suavização anti-tremor). Os quadros entram
  na linha do tempo. Disponível no APK **faceswap** (veja abaixo). Pede consentimento a cada troca e a exportação leva o selo
  **CONTEÚDO ALTERADO • IA**, que não pode ser desligado. Tudo roda no aparelho; o app não traz cenas de filmes (você escolhe o clipe).
- Interface estilo blockbuster: abertura animada, botão-reator, HUD, painéis inclinados.

## Visual e mockup

`docs/mockup/mockup_app.png` mostra as 4 telas (abertura, estúdio ao vivo, efeitos CGI, exportação). A arte de herói
(pistoleiro de cabeça para baixo em "bullet time" com duas submetralhadoras contra um ciborgue de óculos escuros com
escopeta, chuva de código verde, fagulhas e estilhaços) é **vetorial e gerada por código**: `python3 tools/gen_hero_art.py`
emite o SVG do mockup e o `VectorDrawable` do app a partir da mesma descrição. Os personagens são silhuetas genéricas.

## Dois APKs

- `VectorMotion-debug.apk` / `-release.apk`: versão principal, sem dependências de terceiros.
- `VectorMotion-faceswap-debug.apk`: inclui o MediaPipe Face Landmarker (a biblioteca e o modelo `face_landmarker.task` são baixados
  pelo GitHub Actions, que tem acesso à internet; o APK fica algumas dezenas de MB maior). Local: `tools/fetch_face_model.sh` e
  `gradle :app:assembleDebug -PfaceSwap=true`.

## Próximos marcos

- Trilha musical de fundo e transições de áudio.

## Permissões

- Câmera + microfone são pedidos **uma única vez, em um só diálogo, na abertura**. Depois disso o app nunca mais pede nada.
- Armazenamento: **nenhuma permissão** (salva por MediaStore, Android 10).
- O Android **não permite** conceder permissão de câmera sem o aceite do usuário. Para instalar já com tudo concedido
  (sem nem o diálogo), via USB: `adb install -g VectorMotion-debug.apk`.

## Compilar

O sandbox de desenvolvimento não tem Android SDK, então o APK é gerado pelo GitHub Actions
(`.github/workflows/build-vectormotion-android.yml`): *Actions → Vector Motion Android → Run workflow*,
baixe o artifact **VectorMotion-APK** e instale `VectorMotion-debug.apk`.

Localmente (Android Studio ou `gradle :app:assembleDebug` com SDK + NDK):

```sh
cd VectorMotionAndroid
gradle :app:assembleDebug
```

Testes do núcleo C++ (rodam em qualquer Linux):

```sh
g++ -std=c++17 -O1 -fsanitize=address,undefined -Icore/include core/src/*.cpp core/tests/core_tests.cpp -o /tmp/core_tests && /tmp/core_tests
```

## Estrutura

```
core/                 C++17 portátil (timeline, efeitos, RGBA→YUV) + testes de host
app/src/main/cpp/     ponte JNI + CMake do NDK
app/src/main/java/    app (Java, só APIs do framework Android 10)
docs/                 análise de ferramentas e ajustes
```

O APK `release` usa a chave de debug se `VM_KEYSTORE` não estiver definida (instalável, mas **não publicável**
na Play Store; defina `VM_KEYSTORE`, `VM_KEYSTORE_PASSWORD`, `VM_KEY_ALIAS`, `VM_KEY_PASSWORD` para assinar de verdade).
