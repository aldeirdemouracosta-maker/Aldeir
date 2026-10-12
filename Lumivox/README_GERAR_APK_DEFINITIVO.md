# Lumivox Android — APK definitivo instalável

Este pacote contém o projeto Android do Lumivox pronto para compilar no GitHub Actions.

## Resultado esperado no GitHub Actions

Ao rodar o workflow `Gerar APK Lumivox Android`, serão gerados dois arquivos em **Artifacts**:

- `Lumivox-Android-debug.apk` — APK de teste.
- `Lumivox-Android-release-assinado.apk` — APK release assinado, instalável em celulares Android/Xiaomi.

## Como usar

1. Crie um repositório no GitHub, por exemplo `lumivox-android`.
2. Envie todo o conteúdo desta pasta para o repositório.
3. Abra a aba **Actions**.
4. Escolha **Gerar APK Lumivox Android**.
5. Clique em **Run workflow**.
6. Ao finalizar, baixe o artifact **Lumivox-Android-APK**.
7. Extraia o ZIP do artifact e instale `Lumivox-Android-release-assinado.apk` no celular.

## Observação sobre assinatura

O pacote inclui uma chave de assinatura local de protótipo em `app/release/lumivox-release.keystore` para gerar APK instalável imediatamente. Para publicação oficial futura, substitua por uma chave privada definitiva e guarde-a fora do repositório.

## Escopo

Esta versão mantém o núcleo leve do Lumivox:

- HTML5, CSS3 e JavaScript puro em `app/src/main/assets/www`.
- WebView Android offline.
- Ponte nativa `LumivoxAndroid.speak()`.
- TextToSpeech Android em português do Brasil.
- Seletor de arquivos para PDF/imagem via WebChromeClient.
- Interface futurista, alto contraste, botões grandes e foco em acessibilidade.
