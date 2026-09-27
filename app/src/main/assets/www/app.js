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
  pdf(){ $('#filePdf').click(); },
  imagem(){ $('#fileImage').click(); },
  atividade(){
    openModal('CRIAR ATIVIDADE', `
      <label for="subject">TEMA DA ATIVIDADE:</label>
      <input id="subject" value="TABELA PERIODICA" />
      <label for="level">NÍVEL:</label>
      <select id="level"><option>INICIAL</option><option>INTERMEDIÁRIO</option><option>AVANÇADO</option></select>
      <button type="button" class="pill" id="makeActivity">GERAR MODELO</button>
      <div id="activityOut" class="output" aria-live="polite">O MODELO APARECERÁ AQUI.</div>
    `, 'Gerador simples de atividade adaptada.');
    $('#makeActivity').onclick = () => {
      const subject = ($('#subject').value || 'CONTEÚDO').toUpperCase();
      const level = $('#level').value;
      const activity = `ATIVIDADE ADAPTADA - ${subject}\nNÍVEL: ${level}\n\n1. OBSERVE O SÍMBOLO E MARQUE A RESPOSTA CORRETA.\n[   ] OPÇÃO A    [   ] OPÇÃO B    [   ] OPÇÃO C\n\n2. LIGUE O NOME AO SÍMBOLO CORRETO.\n\n3. COMPLETE COM AJUDA DO PROFESSOR.\n\nRECOMENDAÇÕES: LETRA CAIXA ALTA, FONTE GRANDE, ALTO CONTRASTE E POUCOS ITENS POR PÁGINA.`;
      $('#activityOut').textContent = activity;
      saveLibrary(`ATIVIDADE - ${subject}`, activity);
      speak('Atividade criada e salva na biblioteca.');
    };
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
    const text = 'Lumivox é um protótipo acessível. Use os botões grandes. Toque em ouvir texto para ler frases. Use Braille para converter letras. Use calculadora falada para ouvir resultados. Ative alto contraste e fonte ampliada se necessário.';
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
$('#filePdf').addEventListener('change', (e) => {
  const f = e.target.files[0]; if (!f) return;
  const text = `PDF selecionado: ${f.name}. Nesta primeira versão, o aplicativo confirma o arquivo. Para leitura completa de PDF, a próxima etapa é integrar um leitor PDF interno.`;
  openModal('LER PDF', `<p>${escapeHtml(text)}</p>`, text); speak(text); e.target.value = '';
});
$('#fileImage').addEventListener('change', (e) => {
  const f = e.target.files[0]; if (!f) return;
  const text = `Imagem selecionada: ${f.name}. Descrição simulada: arquivo de imagem carregado para análise acessível. A próxima etapa é integrar descrição automática com IA.`;
  openModal('DESCREVER IMAGEM', `<p>${escapeHtml(text)}</p>`, text); speak(text); e.target.value = '';
});

window.addEventListener('load', () => {
  if (safeStorage.getItem('lumivox_contrast') === '1') document.body.classList.add('high-contrast');
  document.documentElement.style.setProperty('--font-scale', safeStorage.getItem('lumivox_font_scale') || '1');
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('service-worker.js').catch(()=>{});
});
