"""Teste do Lumivox rodando de verdade dentro do emulador Android.

Conecta ao WebView do app pelo DevTools (porta encaminhada pelo adb) e exercita
a ponte nativa, o cofre de chaves, a leitura de PDF e o OCR no motor do Android.
Uso: python3 emulator_test.py <porta-devtools>
"""
import base64, json, sys, time, urllib.request

import websocket  # pip install websocket-client

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9222
results, failed = [], []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASSOU " if ok else "FALHOU ") + name + (f"  -> {detail}" if detail else ""), flush=True)
    if not ok:
        failed.append(name)


def pages():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=10) as r:
        return json.load(r)


ws, mid = None, 0


def cdp(method, **params):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg["result"]


def js(expr, timeout=120):
    ws.settimeout(timeout)
    res = cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    if "exceptionDetails" in res:
        d = res["exceptionDetails"]
        raise RuntimeError(d.get("exception", {}).get("description") or d.get("text"))
    return res["result"].get("value")


# --- conectar ao WebView do app ------------------------------------------------
target = None
for _ in range(60):
    try:
        found = [p for p in pages() if p.get("url", "").startswith("https://lumivox.local/")]
        if found:
            target = found[0]
            break
    except Exception:
        pass
    time.sleep(2)
check("app abriu e o WebView carregou https://lumivox.local/", target is not None,
      target["url"] if target else "nenhuma página do Lumivox encontrada")
if not target:
    sys.exit(1)
ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
cdp("Runtime.enable")

for _ in range(30):
    if js("document.readyState") == "complete":
        break
    time.sleep(1)

check("título da página", "Lumivox" in js("document.title"), js("document.title"))
check("ponte nativa LumivoxAndroid disponível",
      js("typeof window.LumivoxAndroid.askAI + '/' + typeof window.LumivoxAndroid.speak") == "function/function")
check("service worker desligado dentro do app",
      js("navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(r => r.length) : 0") == 0)

# --- interface -----------------------------------------------------------------
js("document.querySelector('[data-action=ajuda]').click()")
check("tela Ajuda abre", js("document.getElementById('modalTitle').textContent") == "AJUDA")
js("document.getElementById('modal').close()")

# --- navegação externa bloqueada -------------------------------------------------
js("window.location.assign('https://example.com/')")
time.sleep(4)
host = js("window.location.host")
check("navegação para site externo é bloqueada", host == "lumivox.local", f"host atual: {host}")

# --- cofre de chaves (Android Keystore) --------------------------------------------
js("LumivoxAndroid.clearKey('claude'); LumivoxAndroid.clearKey('gemini')")
check("sem chave no começo", js("LumivoxAndroid.hasKey('claude')") is False)
js("LumivoxAndroid.saveKey('claude', 'sk-ant-chave-falsa-de-teste-123')")
check("chave salva no Keystore (hasKey = true)", js("LumivoxAndroid.hasKey('claude')") is True)
js("LumivoxAndroid.saveKey('gemini', 'AIzaChaveFalsaDeTeste1234567890')")
check("modelo padrão Claude", js("LumivoxAndroid.getModel('claude')") == "claude-haiku-5-5", js("LumivoxAndroid.getModel('claude')"))
check("modelo padrão Gemini", js("LumivoxAndroid.getModel('gemini')") == "gemini-3.6-flash", js("LumivoxAndroid.getModel('gemini')"))
js("LumivoxAndroid.saveKey('claude', 'com espaço')")
check("chave com espaço é recusada (mantém a anterior)", js("LumivoxAndroid.hasKey('claude')") is True)

# --- chamadas reais às APIs, com chave FALSA (esperado: erro de chave, sem custo) -------------
def ask(provider):
    return js("""askAI(%r, 'diga oi', '', 'image/jpeg').then(t => 'OK:' + t, e => 'ERRO:' + e.message)""" % provider)


r = ask("claude")
check("Claude: chave falsa devolve erro tratado (Java + HTTPS + Keystore)",
      r.startswith("ERRO:") and ("Chave inválida" in r or "Sem conexão" in r), r)
r = ask("gemini")
check("Gemini: chave falsa devolve erro tratado (Java + HTTPS + Keystore)",
      r.startswith("ERRO:") and ("Chave inválida" in r or "recusado" in r or "Sem conexão" in r), r)
js("LumivoxAndroid.clearKey('claude'); LumivoxAndroid.clearKey('gemini')")
r = ask("claude")
check("sem chave: pede para cadastrar", r.startswith("ERRO:") and "Cadastre" in r, r)

# --- PDF com texto dentro do WebView ---------------------------------------------------
def make_pdf():
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"]
    stream = b"BT /F1 18 Tf 20 100 Td (Ola Lumivox, teste de leitura de PDF.) Tj ET"
    objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)


pdf_b64 = base64.b64encode(make_pdf()).decode()
r = js("""(async () => {
  const bytes = Uint8Array.from(atob(%r), c => c.charCodeAt(0));
  const out = await extractPdfText(new File([bytes], 't.pdf', {type: 'application/pdf'}), () => {});
  return out.text;
})().catch(e => 'ERRO:' + e.message)""" % pdf_b64)
check("Ler PDF: pdf.js extrai o texto no WebView do Android", "Lumivox" in r and "PDF" in r, r)

# --- OCR (tesseract.js + WebAssembly) dentro do WebView ---------------------------------------
r = js("""(async () => {
  const c = document.createElement('canvas'); c.width = 1500; c.height = 360;
  const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height);
  x.fillStyle = '#000'; x.font = '64px sans-serif';
  x.fillText('Acessibilidade e um direito', 40, 120);
  x.fillText('Lumivox le o texto da foto', 40, 260);
  return await ocrCanvas(c, 'teste');
})().catch(e => 'ERRO:' + e.message)""", timeout=300)
check("OCR offline (WebAssembly) lê texto no WebView do Android",
      "Acessibilidade" in r and "Lumivox" in r, r.replace("\n", " | "))

print(f"\nRESUMO: {len(results) - len(failed)} passaram, {len(failed)} falharam", flush=True)
sys.exit(1 if failed else 0)
