# Lumivox

Meu primeiro aplicativo: um app Android de acessibilidade, feito em HTML, CSS e JavaScript dentro de um WebView, com código Java para a voz, o cofre de chaves e as chamadas de IA.

## O que ele faz

| Função | Precisa de internet? |
|---|---|
| Ouvir texto (voz do Android, em partes, com botão Parar) | não |
| Ler PDF (pdf.js; se for PDF escaneado, lê as páginas como imagem, até 10) | não |
| Ler o texto de uma foto (OCR com tesseract.js) | não |
| Descrever imagem com IA (Claude ou Gemini, com a sua chave) | sim |
| Criar atividade (com IA, ou modelo simples sem IA) | só com IA |
| Braille (conversão básica, ainda não conferida por quem lê Braille) | não |
| Calculadora falada, Biblioteca (guarda localmente), alto contraste, fonte maior | não |

## Privacidade

- A chave de API fica criptografada no cofre do Android (Keystore) e nunca vai para o JavaScript.
- Antes de enviar uma foto à IA, o app avisa para onde ela vai e só envia depois do toque em "Enviar para a IA".
- PDF, OCR, voz, Braille e calculadora funcionam no próprio aparelho.

## Como gerar o APK

1. No GitHub, aba **Actions** > **Gerar APK Lumivox Android** > **Run workflow**.
2. Ao terminar, baixe o artifact **Lumivox-Android-APK** (um zip) e instale o `Lumivox-Android-release-assinado.apk`.
3. O APK é assinado com uma chave de protótipo (`app/release/`). Para publicar numa loja, troque por uma chave privada e guarde-a fora do repositório.

Também dá para compilar no computador: `build_apk_debug.sh` (Linux/macOS) ou `build_apk_debug.bat` (Windows), com Android SDK e Gradle.

## Teste automatizado num Android virtual

Em **Run workflow**, marque **emulator**. O GitHub sobe um Android 14 virtual, instala o app e testa a ponte nativa, o cofre de chaves, o PDF, o OCR e o bloqueio de navegação externa. Não substitui o teste num celular de verdade nem com o TalkBack.

## Pastas

- `app/src/main/java/` – código Android (voz, cofre de chaves, IA, servidor interno dos arquivos).
- `app/src/main/assets/www/` – a interface; `vendor/` guarda pdf.js e tesseract.js (licenças e versões em `VERSION.txt`).
- `ci/` – o teste do emulador.
