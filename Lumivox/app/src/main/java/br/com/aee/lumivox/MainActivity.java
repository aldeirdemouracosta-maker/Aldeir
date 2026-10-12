package br.com.aee.lumivox;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.speech.tts.TextToSpeech;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.view.WindowInsets;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST_CODE = 1001;

    // O app é servido por um endereço https fictício, interceptado aqui e lido dos assets.
    // Assim o WebView não precisa de acesso a file:// e módulos/workers (pdf.js) funcionam.
    private static final String HOST = "lumivox.local";
    private static final String START_URL = "https://" + HOST + "/index.html";

    private static final String DEFAULT_CLAUDE_MODEL = "claude-haiku-5-5";
    private static final String DEFAULT_GEMINI_MODEL = "gemini-3.6-flash";
    private static final int MAX_IMAGE_BASE64 = 7_000_000;
    private static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

    private WebView webView;
    private TextToSpeech textToSpeech;
    private ValueCallback<Uri[]> filePathCallback;
    private SharedPreferences prefs;
    private final ExecutorService executor = Executors.newCachedThreadPool();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        prefs = getSharedPreferences("lumivox_ai", MODE_PRIVATE);
        webView = new WebView(this);
        setContentView(webView);

        // Android 15+ desenha o app sob as barras do sistema: reserva o espaço delas.
        if (Build.VERSION.SDK_INT >= 35) {
            webView.setOnApplyWindowInsetsListener((v, insets) -> {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return insets;
            });
        }

        textToSpeech = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) {
                int result = textToSpeech.setLanguage(new Locale("pt", "BR"));
                if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                    textToSpeech.setLanguage(Locale.getDefault());
                }
            }
        });

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMediaPlaybackRequiresUserGesture(false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return serveAsset(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                // Nunca navega para fora do app (a ponte com a IA só existe para as telas do Lumivox).
                return !HOST.equals(request.getUrl().getHost());
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> filePathCallback,
                                             FileChooserParams fileChooserParams) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;
                Intent intent = fileChooserParams.createIntent();
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE);
                } catch (Exception e) {
                    MainActivity.this.filePathCallback = null;
                    return false;
                }
                return true;
            }
        });

        webView.addJavascriptInterface(new LumivoxBridge(), "LumivoxAndroid");
        webView.loadUrl(START_URL);
    }

    // ---------------------------------------------------------------- assets ---

    private WebResourceResponse serveAsset(Uri uri) {
        if (!"https".equals(uri.getScheme()) || !HOST.equals(uri.getHost())) {
            return errorResponse(403, "Forbidden");
        }
        String path = uri.getPath();
        if (path == null || path.equals("/")) path = "/index.html";
        if (path.contains("..")) return errorResponse(403, "Forbidden");
        try {
            InputStream in = getAssets().open("www" + path);
            return new WebResourceResponse(mimeFor(path), "utf-8", in);
        } catch (IOException e) {
            return errorResponse(404, "Not Found");
        }
    }

    private static WebResourceResponse errorResponse(int code, String reason) {
        return new WebResourceResponse("text/plain", "utf-8", code, reason,
                new HashMap<String, String>(), new ByteArrayInputStream(new byte[0]));
    }

    private static String mimeFor(String path) {
        String p = path.toLowerCase(Locale.ROOT);
        if (p.endsWith(".html")) return "text/html";
        if (p.endsWith(".js") || p.endsWith(".mjs")) return "text/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".json")) return "application/json";
        if (p.endsWith(".webmanifest")) return "application/manifest+json";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".txt")) return "text/plain";
        return "application/octet-stream";
    }

    // ----------------------------------------------------------- ciclo de vida ---

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST_CODE && filePathCallback != null) {
            Uri[] results = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        if (textToSpeech != null) {
            textToSpeech.stop();
            textToSpeech.shutdown();
        }
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    // ------------------------------------------------------------------ voz ---

    /** Divide o texto em pedaços que o TextToSpeech aceita, quebrando em fim de frase quando der. */
    static List<String> splitForSpeech(String text, int limit) {
        List<String> out = new ArrayList<>();
        String rest = text.trim();
        while (!rest.isEmpty()) {
            if (rest.length() <= limit) {
                out.add(rest);
                break;
            }
            int cut = -1;
            for (int i = limit; i > limit / 2; i--) {
                char c = rest.charAt(i - 1);
                if (c == '.' || c == '!' || c == '?' || c == '\n') {
                    cut = i;
                    break;
                }
            }
            if (cut < 0) {
                int space = rest.lastIndexOf(' ', limit);
                cut = space > limit / 2 ? space + 1 : limit;
            }
            out.add(rest.substring(0, cut).trim());
            rest = rest.substring(cut).trim();
        }
        return out;
    }


    // ------------------------------------------------- chaves (Android Keystore) ---

    private static final String KEYSTORE_ALIAS = "lumivox_ai_key";

    private SecretKey keystoreKey() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (!ks.containsAlias(KEYSTORE_ALIAS)) {
            KeyGenerator kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            kg.init(new KeyGenParameterSpec.Builder(KEYSTORE_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build());
            return kg.generateKey();
        }
        return (SecretKey) ks.getKey(KEYSTORE_ALIAS, null);
    }

    /** Criptografa com uma chave que nunca sai do cofre do Android (AES-GCM). */
    private String encryptSecret(String plain) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, keystoreKey());
        byte[] ct = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
        return Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" + Base64.encodeToString(ct, Base64.NO_WRAP);
    }

    private String decryptSecret(String stored) throws Exception {
        String[] parts = stored.split(":");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, keystoreKey(),
                new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }

    /** Lê a chave cadastrada; vazio se não houver ou se não puder ser descriptografada. */
    private String readKey(String provider) {
        String stored = prefs.getString("keyenc_" + provider, "");
        if (stored.isEmpty()) return "";
        try {
            return decryptSecret(stored);
        } catch (Exception e) {
            return "";
        }
    }

    // ------------------------------------------------------------------- IA ---

    private static boolean validProvider(String provider) {
        return "claude".equals(provider) || "gemini".equals(provider);
    }

    private static boolean claudeSupportsEffort(String model) {
        return model.matches("claude-(opus-(4-[5-9]|5.*)|sonnet-(4-[6-9]|5.*)|haiku-5.*|fable-.*)");
    }

    private static class ApiException extends Exception {
        ApiException(String message) {
            super(message);
        }
    }

    private String httpPost(String url, Map<String, String> headers, String body) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setConnectTimeout(15000);
            c.setReadTimeout(90000);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("content-type", "application/json");
            for (Map.Entry<String, String> h : headers.entrySet()) c.setRequestProperty(h.getKey(), h.getValue());
            try (OutputStream os = c.getOutputStream()) {
                os.write(body.getBytes(StandardCharsets.UTF_8));
            }
            int code = c.getResponseCode();
            InputStream in = code < 400 ? c.getInputStream() : c.getErrorStream();
            String text = in == null ? "" : readAll(in);
            if (code >= 400) throw new ApiException(friendlyHttpError(code, text));
            return text;
        } finally {
            c.disconnect();
        }
    }

    private static String readAll(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int n;
        while ((n = in.read(chunk)) > 0) {
            buf.write(chunk, 0, n);
            if (buf.size() > MAX_RESPONSE_BYTES) throw new IOException("Resposta grande demais.");
        }
        return buf.toString("UTF-8");
    }

    private static String friendlyHttpError(int code, String body) {
        if (code == 401 || code == 403) return "Chave inválida ou sem permissão. Confira a chave nas configurações.";
        if (code == 404) return "Modelo não encontrado. Confira o nome do modelo nas configurações.";
        if (code == 429) return "Limite de uso atingido. Tente de novo em instantes.";
        if (code >= 500) return "O serviço da IA está indisponível agora. Tente de novo mais tarde.";
        String detail = "";
        try {
            JSONObject err = new JSONObject(body).optJSONObject("error");
            if (err != null) detail = err.optString("message", "");
        } catch (Exception ignored) {
        }
        if (detail.length() > 200) detail = detail.substring(0, 200);
        return "O pedido foi recusado (erro " + code + ")." + (detail.isEmpty() ? "" : " " + detail);
    }

    private String askClaude(String key, String model, String prompt, String imageB64, String mime) throws Exception {
        JSONArray content = new JSONArray();
        if (!imageB64.isEmpty()) {
            JSONObject source = new JSONObject().put("type", "base64").put("media_type", mime).put("data", imageB64);
            content.put(new JSONObject().put("type", "image").put("source", source));
        }
        content.put(new JSONObject().put("type", "text").put("text", prompt));
        JSONObject body = new JSONObject()
                .put("model", model)
                .put("max_tokens", 4096)
                .put("messages", new JSONArray().put(new JSONObject().put("role", "user").put("content", content)));
        if (claudeSupportsEffort(model)) body.put("output_config", new JSONObject().put("effort", "low"));

        Map<String, String> headers = new HashMap<>();
        headers.put("x-api-key", key);
        headers.put("anthropic-version", "2023-06-01");
        JSONObject r = new JSONObject(httpPost("https://api.anthropic.com/v1/messages", headers, body.toString()));
        if ("refusal".equals(r.optString("stop_reason"))) throw new ApiException("A IA recusou este pedido.");
        StringBuilder sb = new StringBuilder();
        JSONArray blocks = r.optJSONArray("content");
        for (int i = 0; blocks != null && i < blocks.length(); i++) {
            JSONObject b = blocks.getJSONObject(i);
            if ("text".equals(b.optString("type"))) sb.append(b.optString("text"));
        }
        String text = sb.toString().trim();
        if (text.isEmpty()) throw new ApiException("A IA não devolveu texto. Tente de novo.");
        return text;
    }

    private String askGemini(String key, String model, String prompt, String imageB64, String mime) throws Exception {
        JSONArray parts = new JSONArray();
        if (!imageB64.isEmpty()) {
            parts.put(new JSONObject().put("inline_data", new JSONObject().put("mime_type", mime).put("data", imageB64)));
        }
        parts.put(new JSONObject().put("text", prompt));
        JSONObject body = new JSONObject()
                .put("contents", new JSONArray().put(new JSONObject().put("parts", parts)));

        Map<String, String> headers = new HashMap<>();
        headers.put("x-goog-api-key", key);
        String url = "https://generativelanguage.googleapis.com/v1beta/models/"
                + URLEncoder.encode(model, "UTF-8") + ":generateContent";
        JSONObject r = new JSONObject(httpPost(url, headers, body.toString()));
        JSONArray candidates = r.optJSONArray("candidates");
        if (candidates == null || candidates.length() == 0) {
            throw new ApiException("A IA bloqueou ou não respondeu a este conteúdo.");
        }
        JSONArray parts2 = candidates.getJSONObject(0).optJSONObject("content") == null ? null
                : candidates.getJSONObject(0).getJSONObject("content").optJSONArray("parts");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; parts2 != null && i < parts2.length(); i++) sb.append(parts2.getJSONObject(i).optString("text"));
        String text = sb.toString().trim();
        if (text.isEmpty()) throw new ApiException("A IA não devolveu texto. Tente de novo.");
        return text;
    }

    private void deliver(String callbackId, boolean ok, String text) {
        final String js = "window.LumivoxNative && window.LumivoxNative.onResult("
                + JSONObject.quote(callbackId) + "," + ok + "," + JSONObject.quote(text) + ")";
        runOnUiThread(() -> {
            if (webView != null) webView.evaluateJavascript(js, null);
        });
    }

    // ----------------------------------------------------------------- ponte ---

    public class LumivoxBridge {
        @JavascriptInterface
        public void speak(String text) {
            if (textToSpeech == null || text == null || text.trim().isEmpty()) return;
            final List<String> chunks = splitForSpeech(text, Math.min(3500, TextToSpeech.getMaxSpeechInputLength() - 100));
            runOnUiThread(() -> {
                for (int i = 0; i < chunks.size(); i++) {
                    textToSpeech.speak(chunks.get(i), i == 0 ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD,
                            null, "lumivox_utterance_" + i);
                }
            });
        }

        @JavascriptInterface
        public void stopSpeaking() {
            runOnUiThread(() -> {
                if (textToSpeech != null) textToSpeech.stop();
            });
        }

        @JavascriptInterface
        public boolean hasKey(String provider) {
            return validProvider(provider) && !prefs.getString("keyenc_" + provider, "").isEmpty();
        }

        @JavascriptInterface
        public void saveKey(String provider, String key) {
            if (!validProvider(provider) || key == null) return;
            String clean = key.trim();
            if (clean.isEmpty() || clean.length() > 300 || clean.matches(".*\\s.*")) return;
            try {
                prefs.edit().putString("keyenc_" + provider, encryptSecret(clean)).remove("key_" + provider).apply();
            } catch (Exception e) {
                // Sem cofre seguro neste aparelho: não guarda a chave em texto puro.
            }
        }

        @JavascriptInterface
        public void clearKey(String provider) {
            if (validProvider(provider)) prefs.edit().remove("keyenc_" + provider).remove("key_" + provider).apply();
        }

        @JavascriptInterface
        public String getModel(String provider) {
            if (!validProvider(provider)) return "";
            String fallback = "claude".equals(provider) ? DEFAULT_CLAUDE_MODEL : DEFAULT_GEMINI_MODEL;
            return prefs.getString("model_" + provider, fallback);
        }

        @JavascriptInterface
        public void setModel(String provider, String model) {
            if (!validProvider(provider) || model == null) return;
            String clean = model.trim();
            if (clean.isEmpty() || clean.length() > 100 || !clean.matches("[A-Za-z0-9._:-]+")) return;
            prefs.edit().putString("model_" + provider, clean).apply();
        }

        /** Pergunta à IA escolhida (texto e, opcionalmente, uma imagem em base64). O resultado volta por onResult. */
        @JavascriptInterface
        public void askAI(final String provider, final String prompt, final String imageB64,
                          final String mime, final String callbackId) {
            if (callbackId == null) return;
            if (!validProvider(provider)) {
                deliver(callbackId, false, "Escolha Claude ou Gemini.");
                return;
            }
            final String key = readKey(provider);
            if (key.isEmpty()) {
                deliver(callbackId, false, "Cadastre a chave de API nas configurações da IA.");
                return;
            }
            final String image = imageB64 == null ? "" : imageB64;
            if (image.length() > MAX_IMAGE_BASE64) {
                deliver(callbackId, false, "Imagem grande demais.");
                return;
            }
            final String imageMime = "image/png".equals(mime) || "image/webp".equals(mime) ? mime : "image/jpeg";
            final String model = getModel(provider);
            executor.execute(() -> {
                try {
                    String text = "claude".equals(provider)
                            ? askClaude(key, model, prompt, image, imageMime)
                            : askGemini(key, model, prompt, image, imageMime);
                    deliver(callbackId, true, text);
                } catch (ApiException e) {
                    deliver(callbackId, false, e.getMessage());
                } catch (java.net.SocketTimeoutException e) {
                    deliver(callbackId, false, "A IA demorou demais para responder. Tente de novo.");
                } catch (IOException e) {
                    deliver(callbackId, false, "Sem conexão com a internet.");
                } catch (Exception e) {
                    deliver(callbackId, false, "Não foi possível falar com a IA.");
                }
            });
        }
    }
}
