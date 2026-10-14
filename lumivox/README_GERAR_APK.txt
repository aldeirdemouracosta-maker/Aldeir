LUMIVOX - PROJETO ANDROID PRONTO PARA GERAR APK

Status deste pacote:
- Contem um projeto Android nativo com WebView.
- A interface do Lumivox fica em app/src/main/assets/www/.
- A voz no APK foi corrigida para usar TextToSpeech nativo do Android via ponte JavaScript LumivoxAndroid.speak().
- O seletor de arquivos foi preparado para PDF e imagem via WebChromeClient.

Como gerar o APK no Android Studio:
1. Abra o Android Studio.
2. File > Open > selecione a pasta lumivox_android_project.
3. Espere sincronizar o Gradle.
4. Menu Build > Build Bundle(s) / APK(s) > Build APK(s).
5. O APK de teste saira em app/build/outputs/apk/debug/app-debug.apk.
6. Copie para o Xiaomi/Android e instale. Ative permissao para instalar apps desconhecidos se o aparelho pedir.

Como gerar pelo terminal, se tiver Android SDK + Gradle:
- Linux/macOS: ./build_apk_debug.sh
- Windows: build_apk_debug.bat

Observacao importante:
Este ambiente de conversa nao tem Android SDK, Gradle nem a ferramenta aapt/d8 instalados. Por isso o APK final nao pode ser compilado aqui com seguranca. O projeto foi preparado para compilacao no Android Studio.
