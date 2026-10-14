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

**Assinatura:** a chave NÃO fica no repositório (a antiga foi exposta e está descartada). O release assinado exige as variáveis `LUMIVOX_KEYSTORE_PATH`, `LUMIVOX_KEYSTORE_PASSWORD`, `LUMIVOX_KEY_ALIAS` e `LUMIVOX_KEY_PASSWORD`; no GitHub Actions elas vêm dos secrets `LUMIVOX_KEYSTORE_BASE64`, `LUMIVOX_KEYSTORE_PASSWORD`, `LUMIVOX_KEY_PASSWORD` e `LUMIVOX_KEY_ALIAS`. Sem elas só o APK debug é gerado. Atenção: APKs assinados com a chave antiga não são atualizados por APKs da chave nova (é preciso desinstalar).

## Escopo

Esta versão mantém o núcleo leve do Lumivox:

- HTML5, CSS3 e JavaScript puro em `app/src/main/assets/www`.
- WebView Android offline.
- Ponte nativa `LumivoxAndroid.speak()`.
- TextToSpeech Android em português do Brasil.
- Seletor de arquivos para PDF/imagem via WebChromeClient.
- Interface futurista, alto contraste, botões grandes e foco em acessibilidade.
