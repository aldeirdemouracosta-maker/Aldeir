'use strict';

const $ = (sel) => document.querySelector(sel);
const modal = $('#modal');
const modalTitle = $('#modalTitle');
const modalContent = $('#modalContent');
const modalSpeak = $('#modalSpeak');
const statusText = $('#statusText');
let lastModalText = '';

const memoryStore = {};
const safeStorage = {
  getItem(key){
    try { return window.localStorage.getItem(key); }
    catch (_) { return Object.prototype.hasOwnProperty.call(memoryStore, key) ? memoryStore[key] : null; }
  },
  setItem(key, value){
    try { window.localStorage.setItem(key, value); }
    catch (_) { memoryStore[key] = String(value); }
  }
};
window.__lumivoxMemoryStore = memoryStore;

// ---------------------------------------------------------------- ponte nativa / IA ---
const native = window.LumivoxAndroid;
const hasAI = !!(native && typeof native.askAI === 'function');
const AI_PROVIDERS = { claude: 'CLAUDE (ANTHROPIC)', gemini: 'GEMINI (GOOGLE)' };
const pendingAI = {};
window.LumivoxNative = {
  onResult(id, ok, text){
    const done = pendingAI[id]; delete pendingAI[id];
    if (done) done(ok, String(text || ''));
  }
};
function currentProvider(){
  const saved = safeStorage.getItem('lumivox_ai_provider');
  return saved === 'gemini' ? 'gemini' : 'claude';
}
function askAI(provider, prompt, imageB64, mime){
  return new Promise((resolve, reject) => {
    if (!hasAI) return reject(new Error('A IA funciona no aplicativo Android.'));
    const id = 'ai' + Date.now() + Math.random().toString(36).slice(2, 8);
    const timer = setTimeout(() => { delete pendingAI[id]; reject(new Error('A IA demorou demais para responder.')); }, 120000);
    pendingAI[id] = (ok, text) => { clearTimeout(timer); ok ? resolve(text) : reject(new Error(text)); };
    native.askAI(provider, prompt, imageB64 || '', mime || 'image/jpeg', id);
  });
}
function aiSettingsHtml(){
  const provider = currentProvider();
  return `
    <fieldset class="ai-box">
      <legend>CONFIGURAR IA</legend>
      <label for="aiProvider">QUAL IA USAR:</label>
      <select id="aiProvider">
        ${Object.entries(AI_PROVIDERS).map(([k, v]) => `<option value="${k}"${k === provider ? ' selected' : ''}>${v}</option>`).join('')}
      </select>
      <label for="aiKey">CHAVE DE API <span id="aiKeyState"></span>:</label>
      <input id="aiKey" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="COLE SUA CHAVE AQUI" />
      <label for="aiModel">MODELO:</label>
      <input id="aiModel" autocapitalize="off" spellcheck="false" />
      <button type="button" class="pill" id="aiSave">SALVAR</button>
      <button type="button" class="pill" id="aiClear">APAGAR CHAVE</button>
      <small>A chave fica só neste celular. Cada uso da IA é cobrado na sua conta do provedor.</small>
    </fieldset>`;
}
function bindAiSettings(onChange){
  const providerEl = $('#aiProvider'), keyEl = $('#aiKey'), modelEl = $('#aiModel'), stateEl = $('#aiKeyState');
  const refresh = () => {
    const prov = providerEl.value;
    stateEl.textContent = hasAI && native.hasKey(prov) ? '(JÁ CADASTRADA)' : '(NÃO CADASTRADA)';
    modelEl.value = hasAI ? native.getModel(prov) : '';
    keyEl.value = '';
  };
  providerEl.addEventListener('change', () => { safeStorage.setItem('lumivox_ai_provider', providerEl.value); refresh(); onChange && onChange(); });
  $('#aiSave').addEventListener('click', () => {
    if (!hasAI) { setStatus('CONFIGURAÇÃO DE IA SÓ NO APLICATIVO ANDROID.'); return; }
    const prov = providerEl.value;
    safeStorage.setItem('lumivox_ai_provider', prov);
    if (keyEl.value.trim()) native.saveKey(prov, keyEl.value.trim());
    if (modelEl.value.trim()) native.setModel(prov, modelEl.value.trim());
    refresh(); onChange && onChange();
    speak(native.hasKey(prov) ? 'Configuração salva.' : 'Cole a chave de API para usar a IA.');
  });
  $('#aiClear').addEventListener('click', () => {
    if (!hasAI) return;
    native.clearKey(providerEl.value); refresh(); onChange && onChange(); speak('Chave apagada.');
  });
  refresh();
}
function stopSpeaking(){
  if (native && typeof native.stopSpeaking === 'function') native.stopSpeaking();
  else if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  setStatus('LEITURA PARADA.');
}
async function fileToJpegBase64(file, maxSide = 1568){
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bmp.width * scale));
  canvas.height = Math.max(1, Math.round(bmp.height * scale));
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
  if (bmp.close) bmp.close();
  return canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
}
async function extractPdfText(file, onProgress){
  const pdfjs = await import('./vendor/pdfjs/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdfjs/pdf.worker.min.mjs', window.location.href).href;
  const data = new Uint8Array(await file.arrayBuffer());
  const pdf = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
  const pages = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    onProgress && onProgress(n, pdf.numPages);
    const page = await pdf.getPage(n);
    const content = await page.getTextContent();
    let line = '';
    for (const item of content.items) {
      line += item.str;
      line += item.hasEOL ? '\n' : (item.str && !item.str.endsWith(' ') ? ' ' : '');
    }
    pages.push(line.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim());
  }
  return { text: pages.filter(Boolean).join('\n\n'), pages: pdf.numPages };
}

// ------------------------------------------------- leitura de texto (OCR) offline ---
let ocrWorkerPromise = null;
function withTimeout(promise, ms, message){
  let timer;
  const limit = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(message)), ms); });
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
}
let ocrLogger = null;
function loadScript(src){
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src; el.onload = resolve;
    el.onerror = () => reject(new Error('Não foi possível carregar o leitor de texto.'));
    document.head.appendChild(el);
  });
}
function getOcrWorker(){
  if (!ocrWorkerPromise) {
    ocrWorkerPromise = withTimeout((async () => {
      if (!window.Tesseract) await loadScript('./vendor/tesseract/tesseract.min.js');
      const base = new URL('./vendor/tesseract/', window.location.href).href;
      return window.Tesseract.createWorker('por', 1, {
        workerPath: base + 'worker.min.js', corePath: base, langPath: base + 'lang',
        cacheMethod: 'none', workerBlobURL: false, gzip: false,
        logger: (m) => { if (ocrLogger) ocrLogger(m); }
      });
    })(), 120000, 'O leitor de texto demorou demais para iniciar.').catch((e) => { ocrWorkerPromise = null; throw e; });
  }
  return ocrWorkerPromise;
}
async function fileToCanvas(file, maxSide = 2200){
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bmp.width * scale));
  canvas.height = Math.max(1, Math.round(bmp.height * scale));
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
  if (bmp.close) bmp.close();
  return canvas;
}
async function ocrCanvas(canvas, label){
  ocrLogger = (m) => {
    if (m.status === 'recognizing text') setStatus(`${label} ${Math.round((m.progress || 0) * 100)}%`);
    else if (m.status && m.status.startsWith('loading')) setStatus('PREPARANDO O LEITOR DE TEXTO...');
  };
  const worker = await getOcrWorker();
  const { data } = await withTimeout(worker.recognize(canvas), 240000, 'A leitura do texto demorou demais.');
  return String(data.text || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}
async function ocrPdfPages(file, maxPages, onProgress){
  const pdfjs = await import('./vendor/pdfjs/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdfjs/pdf.worker.min.mjs', window.location.href).href;
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()), isEvalSupported: false }).promise;
  const total = Math.min(pdf.numPages, maxPages), parts = [];
  for (let n = 1; n <= total; n++) {
    onProgress && onProgress(n, total);
    const page = await pdf.getPage(n);
    const viewport = page.getViewport({ scale: Math.min(2.5, 2200 / Math.max(page.getViewport({ scale: 1 }).width, page.getViewport({ scale: 1 }).height) * 1.0) });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(viewport.width); canvas.height = Math.round(viewport.height);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
    parts.push(await ocrCanvas(canvas, `LENDO PÁGINA ${n} DE ${total}:`));
  }
  return { text: parts.filter(Boolean).join('\n\n'), pages: total, totalPages: pdf.numPages };
}

const DESCRIBE_PROMPT = 'Você é um audiodescritor que ajuda uma pessoa cega. Descreva esta imagem em português do Brasil, em texto corrido e sem Markdown. ' +
  'Comece dizendo o que é a imagem (foto, documento, captura de tela, desenho...) em uma frase. Depois descreva as pessoas, objetos, cores, posições e o ambiente, do mais importante para o menos importante. ' +
  'Se houver texto ou números, transcreva exatamente o que está escrito. Se for um documento, tabela ou gráfico, explique a estrutura e os valores. ' +
  'Descreva só o que realmente aparece: não invente nem adivinhe o que não dá para ver, e avise se algo estiver ilegível ou cortado.';


const brailleMap = {
  'a':'⠁','b':'⠃','c':'⠉','d':'⠙','e':'⠑','f':'⠋','g':'⠛','h':'⠓','i':'⠊','j':'⠚',
  'k':'⠅','l':'⠇','m':'⠍','n':'⠝','o':'⠕','p':'⠏','q':'⠟','r':'⠗','s':'⠎','t':'⠞',
  'u':'⠥','v':'⠧','w':'⠺','x':'⠭','y':'⠽','z':'⠵','ç':'⠯','á':'⠷','é':'⠮','í':'⠌','ó':'⠬','ú':'⠾','ã':'⠜','õ':'⠪','â':'⠡','ê':'⠣','ô':'⠹',
  '1':'⠼⠁','2':'⠼⠃','3':'⠼⠉','4':'⠼⠙','5':'⠼⠑','6':'⠼⠋','7':'⠼⠛','8':'⠼⠓','9':'⠼⠊','0':'⠼⠚',
  ' ':'  ','.':'⠲',',':'⠂',';':'⠆',':':'⠒','?':'⠦','!':'⠖','-':'⠤','(':'⠣',')':'⠜','/':'⠌'
};

function speak(text){
  const clean = String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  if (!clean) return;

  // APK Android: usa voz nativa via ponte Java/Kotlin para funcionar melhor no WebView.
  if (window.LumivoxAndroid && typeof window.LumivoxAndroid.speak === 'function') {
    window.LumivoxAndroid.speak(clean);
    setStatus('LUMIVOX ESTÁ FALANDO...');
    return;
  }

  // PWA/Navegador: usa a API de fala do navegador quando disponível.
  if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
    setStatus('VOZ NÃO DISPONÍVEL NESTE NAVEGADOR.');
    return;
  }
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = 'pt-BR';
  utter.rate = 0.92;
  utter.pitch = 1;
  window.speechSynthesis.speak(utter);
  setStatus('LUMIVOX ESTÁ FALANDO...');
}

function setStatus(text){ statusText.textContent = String(text).toUpperCase(); }
function escapeHtml(str){ return String(str).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function openModal(title, html, speakText){
  modalTitle.textContent = title;
  modalContent.innerHTML = html;
  lastModalText = speakText || modalContent.innerText || title;
  if (typeof modal.showModal === 'function') modal.showModal(); else alert(lastModalText);
}
function saveLibrary(title, content){
  const items = JSON.parse(safeStorage.getItem('lumivox_library') || '[]');
  items.unshift({title, content, date: new Date().toLocaleString('pt-BR')});
  safeStorage.setItem('lumivox_library', JSON.stringify(items.slice(0, 30)));
}
function convertBraille(text){
  return Array.from(String(text).toLowerCase()).map(ch => brailleMap[ch] || '□').join('');
}
function safeEvalMath(expression){
  const normalized = String(expression).replace(',', '.').replace(/×/g, '*').replace(/÷/g, '/');
  if (!/^[0-9+\-*/().%\s]+$/.test(normalized)) throw new Error('Use apenas números e sinais de conta.');
  // eslint-disable-next-line no-new-func
  const result = Function(`"use strict"; return (${normalized});`)();
  if (!Number.isFinite(result)) throw new Error('Resultado inválido.');
  return result;
}
function downloadText(filename, text){
  const blob = new Blob([text], {type:'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

const actions = {
  texto(){
    openModal('OUVIR TEXTO', `
      <label for="textToRead">DIGITE OU COLE O TEXTO:</label>
      <textarea id="textToRead" placeholder="EXEMPLO: BOM DIA. VAMOS ESTUDAR COM O LUMIVOX."></textarea>
      <button type="button" class="pill" id="readTextBtn">🔊 LER TEXTO</button>
    `, 'Digite um texto e toque em ler texto.');
    $('#readTextBtn').onclick = () => speak($('#textToRead').value || 'Digite um texto para ouvir.');
  },
  pdf(){
    openModal('LER PDF', `
      <p>ESCOLHA UM PDF E O LUMIVOX LÊ O TEXTO EM VOZ ALTA. FUNCIONA SEM INTERNET.</p>
      <button type="button" class="pill" id="pickPdf">📄 ESCOLHER PDF</button>
      <div id="pdfOut" class="output" aria-live="polite">O TEXTO APARECERÁ AQUI.</div>
      <button type="button" class="pill" id="pdfRead" hidden>🔊 LER EM VOZ ALTA</button>
    `, 'Escolha um PDF para ouvir o texto.');
    $('#pickPdf').onclick = () => $('#filePdf').click();
  },
  imagem(){
    openModal('DESCREVER IMAGEM', `
      <p>ESCOLHA UMA FOTO OU IMAGEM E UMA IA DESCREVE PARA VOCÊ. PRECISA DE INTERNET E DA SUA CHAVE DE API.</p>
      <button type="button" class="pill" id="pickOcr">🔤 LER O TEXTO DA FOTO (SEM INTERNET, A FOTO NÃO SAI DO CELULAR)</button>
      <button type="button" class="pill" id="pickImage">📷 DESCREVER COM IA (ENVIA A FOTO)</button>
      <div id="imageOut" class="output" aria-live="polite">A DESCRIÇÃO APARECERÁ AQUI.</div>
      <button type="button" class="pill" id="imageSend" hidden>📤 ENVIAR PARA A IA</button>
      <button type="button" class="pill" id="imageCancel" hidden>CANCELAR</button>
      <button type="button" class="pill" id="imageRead" hidden>🔊 OUVIR DESCRIÇÃO</button>
      ${aiSettingsHtml()}
    `, 'Escolha uma imagem para ouvir a descrição.');
    $('#pickOcr').onclick = () => { imageMode = 'ocr'; $('#fileImage').click(); };
    $('#pickImage').onclick = () => {
      imageMode = 'ai';
      if (!hasAI) { $('#imageOut').textContent = 'A DESCRIÇÃO POR IA FUNCIONA NO APLICATIVO ANDROID.'; return; }
      if (!native.hasKey(currentProvider())) {
        $('#imageOut').textContent = 'CADASTRE A CHAVE DE API ABAIXO PARA USAR A IA.'; speak('Cadastre a chave de API abaixo.'); return;
      }
      $('#fileImage').click();
    };
    $('#imageSend').onclick = sendPendingImage;
    $('#imageCancel').onclick = () => { pendingImage = null; $('#imageSend').hidden = true; $('#imageCancel').hidden = true; $('#imageOut').textContent = 'ENVIO CANCELADO.'; speak('Envio cancelado.'); };
    bindAiSettings();
  },
  atividade(){
    openModal('CRIAR ATIVIDADE', `
      <label for="subject">TEMA DA ATIVIDADE:</label>
      <input id="subject" value="TABELA PERIODICA" />
      <label for="level">NÍVEL:</label>
      <select id="level"><option>INICIAL</option><option>INTERMEDIÁRIO</option><option>AVANÇADO</option></select>
      <button type="button" class="pill" id="makeActivityAI">✨ GERAR COM IA</button>
      <button type="button" class="pill" id="makeActivity">MODELO SIMPLES (SEM IA)</button>
      <div id="activityOut" class="output" aria-live="polite">A ATIVIDADE APARECERÁ AQUI.</div>
      ${aiSettingsHtml()}
    `, 'Gerador de atividade adaptada.');
    const read = () => ({ subject: ($('#subject').value || 'CONTEÚDO').toUpperCase(), level: $('#level').value });
    const show = (subject, activity) => { $('#activityOut').textContent = activity; saveLibrary(`ATIVIDADE - ${subject}`, activity); lastModalText = activity; };
    $('#makeActivity').onclick = () => {
      const { subject, level } = read();
      show(subject, `ATIVIDADE ADAPTADA - ${subject}\nNÍVEL: ${level}\n\n1. OBSERVE O SÍMBOLO E MARQUE A RESPOSTA CORRETA.\n[   ] OPÇÃO A    [   ] OPÇÃO B    [   ] OPÇÃO C\n\n2. LIGUE O NOME AO SÍMBOLO CORRETO.\n\n3. COMPLETE COM AJUDA DO PROFESSOR.\n\nRECOMENDAÇÕES: LETRA CAIXA ALTA, FONTE GRANDE, ALTO CONTRASTE E POUCOS ITENS POR PÁGINA.`);
      speak('Modelo criado e salvo na biblioteca.');
    };
    $('#makeActivityAI').onclick = async () => {
      if (!hasAI || !native.hasKey(currentProvider())) {
        $('#activityOut').textContent = 'CADASTRE A CHAVE DE API ABAIXO PARA GERAR COM IA, OU USE O MODELO SIMPLES.'; speak('Cadastre a chave de API abaixo.'); return;
      }
      const { subject, level } = read();
      $('#activityOut').textContent = 'GERANDO...'; setStatus('GERANDO ATIVIDADE...');
      try {
        const prompt = `Crie uma atividade escolar adaptada para estudantes cegos ou com baixa visão sobre "${subject}", nível ${level.toLowerCase()}. ` +
          'Use frases curtas, letras em caixa alta, no máximo 5 questões simples e, no final, o gabarito. Não dependa de figuras nem de cores. ' +
          'Responda em português do Brasil, em texto simples, sem Markdown.';
        show(subject, await askAI(currentProvider(), prompt));
        speak('Atividade criada e salva na biblioteca.');
      } catch (e) { $('#activityOut').textContent = 'ERRO: ' + e.message; speak('Não consegui gerar a atividade. ' + e.message); }
    };
    bindAiSettings();
  },
  braille(){
    openModal('BRAILLE', `
      <label for="brailleText">TEXTO PARA CONVERTER:</label>
      <textarea id="brailleText" placeholder="SOFIA LUCAS NINA"></textarea>
      <button type="button" class="pill" id="convertBraille">CONVERTER</button>
      <div id="brailleOut" class="output" aria-live="polite">O BRAILLE APARECERÁ AQUI.</div>
    `, 'Conversor básico para Braille Unicode.');
    $('#convertBraille').onclick = () => {
      const text = $('#brailleText').value || '';
      const out = convertBraille(text);
      $('#brailleOut').textContent = out || 'DIGITE UM TEXTO.';
      speak(out ? 'Texto convertido em Braille.' : 'Digite um texto para converter.');
    };
  },
  calc(){
    openModal('CALCULADORA FALADA', `
      <label for="calcInput">DIGITE A CONTA:</label>
      <input id="calcInput" inputmode="decimal" placeholder="EXEMPLO: 12 + 8 * 2" />
      <button type="button" class="pill" id="calcBtn">CALCULAR E FALAR</button>
      <div id="calcOut" class="output" aria-live="polite">RESULTADO.</div>
    `, 'Calculadora falada.');
    $('#calcBtn').onclick = () => {
      try{
        const result = safeEvalMath($('#calcInput').value || '0');
        $('#calcOut').textContent = `RESULTADO: ${String(result).replace('.', ',')}`;
        speak(`O resultado é ${String(result).replace('.', ',')}`);
      }catch(e){ $('#calcOut').textContent = 'ERRO: ' + e.message; speak('Erro na conta. Verifique os números e sinais.'); }
    };
  },
  biblioteca(){
    const items = JSON.parse(safeStorage.getItem('lumivox_library') || '[]');
    const html = items.length ? items.map((it,i)=>`<article class="output"><strong>${i+1}. ${escapeHtml(it.title)}</strong><br><small>${escapeHtml(it.date)}</small><br>${escapeHtml(it.content)}</article>`).join('<br>') : '<p>NENHUMA ATIVIDADE SALVA AINDA. USE O BOTÃO CRIAR ATIVIDADE.</p>';
    openModal('BIBLIOTECA', html, items.length ? 'Biblioteca aberta com atividades salvas.' : 'Biblioteca vazia.');
  },
  ajuda(){
    const text = 'Lumivox é um protótipo acessível. Use os botões grandes. Toque em ouvir texto para ler frases. Use ler PDF para ouvir documentos. Use descrever imagem para ler o texto de uma foto sem internet, ou para ouvir a descrição dela com a sua chave de inteligência artificial. Use Braille para converter letras. Use calculadora falada para ouvir resultados. Ative alto contraste e fonte ampliada se necessário.';
    openModal('AJUDA', `<p>${escapeHtml(text)}</p><p><strong>DICA:</strong> NO ANDROID, ABRA PELO CHROME E USE A OPÇÃO “ADICIONAR À TELA INICIAL”.</p>`, text);
  }
};

document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  setStatus(`ABRINDO ${btn.innerText.replace(/\s+/g,' ')}`);
  actions[action]?.();
});

$('#modalSpeak').addEventListener('click', () => speak(lastModalText));
$('#modalStop').addEventListener('click', stopSpeaking);
$('#speakIntro').addEventListener('click', () => speak('Menu principal. Ouvir texto. Ler PDF. Descrever imagem. Criar atividade. Braille. Calculadora falada. Biblioteca. Ajuda.'));
$('#voiceBtn').addEventListener('click', () => speak('Olá. Eu sou o Lumivox. Escolha uma opção no menu.'));
$('#contrastToggle').addEventListener('click', () => {
  document.body.classList.toggle('high-contrast');
  const on = document.body.classList.contains('high-contrast');
  safeStorage.setItem('lumivox_contrast', on ? '1':'0');
  speak(on ? 'Alto contraste ativado.' : 'Alto contraste desativado.');
});
$('#fontToggle').addEventListener('click', () => {
  const current = document.documentElement.style.getPropertyValue('--font-scale') || '1';
  const next = Number(current) >= 1.22 ? 1 : 1.22;
  document.documentElement.style.setProperty('--font-scale', String(next));
  safeStorage.setItem('lumivox_font_scale', String(next));
  speak(next > 1 ? 'Fonte ampliada.' : 'Fonte normal.');
});
$('#settingsBtn').addEventListener('click', () => {
  openModal('ACESSIBILIDADE', `
    <div class="settings-grid">
      <div class="setting-row"><span>ALTO CONTRASTE</span><button type="button" onclick="document.getElementById('contrastToggle').click()">ALTERAR</button></div>
      <div class="setting-row"><span>FONTE AMPLIADA</span><button type="button" onclick="document.getElementById('fontToggle').click()">ALTERAR</button></div>
      <div class="setting-row"><span>LEITURA DO MENU</span><button type="button" onclick="document.getElementById('speakIntro').click()">OUVIR</button></div>
    </div>
  `, 'Recursos de acessibilidade. Alto contraste. Fonte ampliada. Leitura do menu.');
});
$('#filePdf').addEventListener('change', async (e) => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  const out = $('#pdfOut');
  if (!out) return;
  out.textContent = 'LENDO O PDF...'; setStatus('LENDO O PDF...');
  try {
    const { text, pages } = await extractPdfText(f, (n, total) => setStatus(`LENDO PÁGINA ${n} DE ${total}...`));
    if (!text) {
      out.textContent = 'ESTE PDF NÃO TEM TEXTO DIGITAL (PARECE SER ESCANEADO). VOU TENTAR LER AS PÁGINAS COMO IMAGEM, ATÉ 10 PÁGINAS. PODE DEMORAR.';
      speak('Este PDF parece escaneado. Vou tentar ler as páginas como imagem. Pode demorar.');
      const scanned = await ocrPdfPages(f, 10, (n, total) => setStatus(`PREPARANDO PÁGINA ${n} DE ${total}...`));
      if (!scanned.text) { out.textContent = 'NÃO ENCONTREI TEXTO LEGÍVEL NESTE PDF.'; speak('Não encontrei texto legível neste PDF.'); return; }
      const note = scanned.totalPages > scanned.pages ? `\n\n[LIDAS AS ${scanned.pages} PRIMEIRAS DE ${scanned.totalPages} PÁGINAS]` : '';
      out.textContent = scanned.text + note; lastModalText = scanned.text;
      const btn2 = $('#pdfRead'); btn2.hidden = false; btn2.onclick = () => speak(scanned.text);
      setStatus('PDF PRONTO.'); speak(scanned.text); return;
    }
    const LIMIT = 30000;
    out.textContent = text.length > LIMIT ? text.slice(0, LIMIT) + '\n\n[... TEXTO MOSTRADO ATÉ AQUI; A LEITURA EM VOZ CONTINUA ATÉ O FIM ...]' : text;
    lastModalText = text;
    const btn = $('#pdfRead'); btn.hidden = false; btn.onclick = () => speak(text);
    setStatus(`PDF PRONTO: ${pages} PÁGINA(S).`);
    speak(`PDF pronto, ${pages} página${pages > 1 ? 's' : ''}. ` + text);
  } catch (err) {
    out.textContent = 'NÃO FOI POSSÍVEL LER ESTE PDF. ELE PODE ESTAR PROTEGIDO POR SENHA OU DANIFICADO.';
    speak('Não foi possível ler este PDF.');
  }
});
let pendingImage = null;
let imageMode = 'ai';
const PRIVACY_NOTE = {
  claude: 'SERÁ ENVIADA À ANTHROPIC (CLAUDE). O USO É COBRADO NA SUA CONTA.',
  gemini: 'SERÁ ENVIADA AO GOOGLE (GEMINI). NA CAMADA GRATUITA, O GOOGLE PODE USAR O CONTEÚDO PARA MELHORAR SEUS PRODUTOS; NA PAGA, NÃO.'
};
async function sendPendingImage(){
  const f = pendingImage; pendingImage = null;
  const out = $('#imageOut'), sendBtn = $('#imageSend'), cancelBtn = $('#imageCancel');
  if (!f || !out) return;
  if (sendBtn) sendBtn.hidden = true; if (cancelBtn) cancelBtn.hidden = true;
  out.textContent = 'DESCREVENDO A IMAGEM...'; setStatus('DESCREVENDO A IMAGEM...'); speak('Descrevendo a imagem. Aguarde.');
  try {
    const b64 = await fileToJpegBase64(f); // recodificar remove os metadados da foto (como a localização)
    const text = await askAI(currentProvider(), DESCRIBE_PROMPT, b64, 'image/jpeg');
    out.textContent = text; lastModalText = text;
    const btn = $('#imageRead'); btn.hidden = false; btn.onclick = () => speak(text);
    saveLibrary(`DESCRIÇÃO - ${f.name || 'IMAGEM'}`, text);
    setStatus('DESCRIÇÃO PRONTA.'); speak(text);
  } catch (err) {
    out.textContent = 'ERRO: ' + err.message; setStatus('ERRO NA DESCRIÇÃO.'); speak('Não consegui descrever a imagem. ' + err.message);
  }
}
$('#fileImage').addEventListener('change', (e) => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  const out = $('#imageOut');
  if (!out) return;
  if (imageMode === 'ocr') {
    out.textContent = 'LENDO O TEXTO DA FOTO... (A FOTO NÃO SAI DO CELULAR)'; setStatus('LENDO O TEXTO DA FOTO...');
    speak('Lendo o texto da foto. Aguarde.');
    fileToCanvas(f).then((canvas) => ocrCanvas(canvas, 'LENDO O TEXTO:')).then((text) => {
      if (!text) { out.textContent = 'NÃO ENCONTREI TEXTO NESTA FOTO. TENTE COM MAIS LUZ E O TEXTO CENTRALIZADO.'; speak('Não encontrei texto nesta foto.'); return; }
      out.textContent = text; lastModalText = text;
      const btn = $('#imageRead'); btn.hidden = false; btn.onclick = () => speak(text);
      setStatus('TEXTO PRONTO.'); speak(text);
    }).catch(() => { out.textContent = 'NÃO FOI POSSÍVEL LER O TEXTO DESTA FOTO.'; speak('Não foi possível ler o texto desta foto.'); });
    return;
  }
  pendingImage = f;
  const prov = currentProvider();
  const msg = `FOTO ESCOLHIDA. ELA ${PRIVACY_NOTE[prov]}\nOS DADOS DA LOCALIZAÇÃO DA FOTO NÃO SÃO ENVIADOS.\n\nTOQUE EM "ENVIAR PARA A IA" PARA CONTINUAR.`;
  out.textContent = msg;
  $('#imageSend').hidden = false; $('#imageCancel').hidden = false;
  speak('Foto escolhida. ' + (prov === 'gemini' ? 'Ela será enviada ao Google.' : 'Ela será enviada à Anthropic.') + ' Toque em enviar para a IA para continuar, ou em cancelar.');
});
modal.addEventListener('close', stopSpeaking);

window.addEventListener('load', () => {
  if (safeStorage.getItem('lumivox_contrast') === '1') document.body.classList.add('high-contrast');
  document.documentElement.style.setProperty('--font-scale', safeStorage.getItem('lumivox_font_scale') || '1');
  if (!native && 'serviceWorker' in navigator) navigator.serviceWorker.register('service-worker.js').catch(()=>{});
});
