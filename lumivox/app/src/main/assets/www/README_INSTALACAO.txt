LUMIVOX - ASSISTENTE ACESSIVEL
Versao inicial: PWA instalavel para celular Android e computador

COMO TESTAR NO COMPUTADOR
1. Extraia o arquivo lumivox_app.zip.
2. Abra o arquivo index.html no navegador.
3. Teste os botoes: OUVIR TEXTO, BRAILLE, CALCULADORA FALADA e CRIAR ATIVIDADE.

COMO USAR COMO APLICATIVO NO CELULAR ANDROID
Opcao simples para teste local:
1. Extraia a pasta no celular ou envie a pasta para um servidor/local hospedado.
2. Abra o index.html no Chrome.
3. Toque no menu do Chrome: tres pontos.
4. Escolha: ADICIONAR A TELA INICIAL.
5. O Lumivox aparecera como icone de aplicativo.

OBSERVACAO IMPORTANTE
Para instalar como PWA completo com cache offline e icone correto, o ideal e hospedar a pasta em um endereco HTTPS. Em servidor HTTPS, o arquivo manifest.webmanifest e o service-worker.js permitem instalacao como aplicativo.

RECURSOS FUNCIONAIS NESTA VERSAO
- Interface futurista e acessivel.
- Botoes grandes e em caixa alta.
- Voz por speechSynthesis do navegador.
- Alto contraste.
- Fonte ampliada.
- Conversor Braille Unicode basico.
- Calculadora falada.
- Gerador simples de atividade adaptada.
- Biblioteca local para atividades geradas.
- Manifest PWA e service worker.

RECURSOS SIMULADOS / PROXIMA ETAPA
- LER PDF: seleciona arquivo e confirma o nome; a leitura completa exige integrar leitor PDF interno.
- DESCREVER IMAGEM: seleciona imagem e simula descricao; descricao real exige integrar IA/OCR.
- APK nativo: pode ser gerado depois usando Capacitor ou Android Studio a partir desta base.
