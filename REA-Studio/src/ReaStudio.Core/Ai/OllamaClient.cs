using System.Net.Http.Json;
using System.Text.Json;

namespace ReaStudio.Core.Ai;

public enum ToolSupport { Unknown, Declared, NotDeclared }

/// <summary>Dados reais do Ollama. EstimatedMemoryBytes é estimativa (tamanho em disco x 1,2), não medição.</summary>
public sealed record OllamaModelInfo(string Name, long SizeBytes, string? ParameterSize, string? Quantization,
    long EstimatedMemoryBytes, int? MaxContext, int? ConfiguredContext, ToolSupport Tools, bool LoadedNow);

public sealed record OllamaDiscovery(bool Reachable, string Detail, IReadOnlyList<OllamaModelInfo> Models);

public sealed class OllamaClient
{
    public static readonly Uri DefaultBase = new("http://127.0.0.1:11434/");
    public const string PreferredModel = "gpt-oss:20b";

    readonly HttpClient _http;
    readonly Uri _base;

    public OllamaClient(HttpClient http, Uri? baseUri = null) { _http = http; _base = baseUri ?? DefaultBase; }

    public async Task<OllamaDiscovery> DiscoverAsync(CancellationToken ct)
    {
        try
        {
            using var tags = await _http.GetAsync(new Uri(_base, "api/tags"), ct).ConfigureAwait(false);
            if (!tags.IsSuccessStatusCode)
                return new OllamaDiscovery(false, $"Ollama respondeu HTTP {(int)tags.StatusCode}", Array.Empty<OllamaModelInfo>());
            using var doc = JsonDocument.Parse(await tags.Content.ReadAsStringAsync(ct).ConfigureAwait(false));
            var loaded = await LoadedNamesAsync(ct).ConfigureAwait(false);
            var list = new List<OllamaModelInfo>();
            if (doc.RootElement.TryGetProperty("models", out var models))
                foreach (var m in models.EnumerateArray())
                {
                    var name = m.GetProperty("name").GetString() ?? "";
                    long size = m.TryGetProperty("size", out var s) ? s.GetInt64() : 0;
                    string? psize = null, quant = null;
                    if (m.TryGetProperty("details", out var d))
                    {
                        psize = d.TryGetProperty("parameter_size", out var p) ? p.GetString() : null;
                        quant = d.TryGetProperty("quantization_level", out var q) ? q.GetString() : null;
                    }
                    var (maxCtx, cfgCtx, tools) = await ShowAsync(name, ct).ConfigureAwait(false);
                    list.Add(new OllamaModelInfo(name, size, psize, quant, (long)(size * 1.2), maxCtx, cfgCtx, tools, loaded.Contains(name)));
                }
            return new OllamaDiscovery(true, $"{list.Count} modelo(s) instalado(s)", list);
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException or KeyNotFoundException
                                    || (ex is OperationCanceledException && !ct.IsCancellationRequested))
        {
            return new OllamaDiscovery(false, "Ollama inacessível em " + _base.Authority, Array.Empty<OllamaModelInfo>());
        }
    }

    async Task<HashSet<string>> LoadedNamesAsync(CancellationToken ct)
    {
        var set = new HashSet<string>();
        try
        {
            using var r = await _http.GetAsync(new Uri(_base, "api/ps"), ct).ConfigureAwait(false);
            if (!r.IsSuccessStatusCode) return set;
            using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync(ct).ConfigureAwait(false));
            if (doc.RootElement.TryGetProperty("models", out var ms))
                foreach (var m in ms.EnumerateArray())
                    if (m.TryGetProperty("name", out var n) && n.GetString() is { } s) set.Add(s);
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException) { }
        return set;
    }

    async Task<(int? max, int? cfg, ToolSupport tools)> ShowAsync(string model, CancellationToken ct)
    {
        try
        {
            using var r = await _http.PostAsJsonAsync(new Uri(_base, "api/show"), new { model }, ct).ConfigureAwait(false);
            if (!r.IsSuccessStatusCode) return (null, null, ToolSupport.Unknown);
            using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync(ct).ConfigureAwait(false));
            var root = doc.RootElement;
            int? max = null, cfg = null;
            if (root.TryGetProperty("model_info", out var mi))
                foreach (var p in mi.EnumerateObject())
                    if (p.Name.EndsWith(".context_length", StringComparison.Ordinal) && p.Value.TryGetInt32(out var v)) max = v;
            if (root.TryGetProperty("parameters", out var pr) && pr.GetString() is { } text)
                foreach (var line in text.Split('\n'))
                {
                    var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length == 2 && parts[0] == "num_ctx" && int.TryParse(parts[1], out var n)) cfg = n;
                }
            var tools = ToolSupport.Unknown;
            if (root.TryGetProperty("capabilities", out var caps) && caps.ValueKind == JsonValueKind.Array)
                tools = caps.EnumerateArray().Any(c => c.GetString() == "tools") ? ToolSupport.Declared : ToolSupport.NotDeclared;
            return (max, cfg, tools);
        }
        catch (Exception ex) when (ex is HttpRequestException or JsonException) { return (null, null, ToolSupport.Unknown); }
    }

    /// <summary>gpt-oss:20b se instalado; senão o primeiro com ferramentas declaradas; senão o primeiro.</summary>
    public static OllamaModelInfo? SelectPreferred(IReadOnlyList<OllamaModelInfo> models)
        => models.FirstOrDefault(m => m.Name == PreferredModel)
           ?? models.FirstOrDefault(m => m.Tools == ToolSupport.Declared)
           ?? models.FirstOrDefault();

    public async Task<AiResult> ChatAsync(AiRequest request, CancellationToken ct)
    {
        try
        {
            using var r = await _http.PostAsJsonAsync(new Uri(_base, "api/chat"), new
            {
                model = request.Model,
                stream = false,
                messages = request.Messages.Select(m => new { role = m.Role, content = m.Content })
            }, ct).ConfigureAwait(false);
            var body = await r.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            if (!r.IsSuccessStatusCode)
                return AiResult.Fail(ProviderId.Ollama, request.Model,
                    r.StatusCode == System.Net.HttpStatusCode.NotFound ? AiErrorKind.Unknown : ErrorClassifier.FromHttp((int)r.StatusCode, body),
                    $"HTTP {(int)r.StatusCode}");
            using var doc = JsonDocument.Parse(body);
            return new AiResult(true, doc.RootElement.GetProperty("message").GetProperty("content").GetString() ?? "",
                ProviderId.Ollama, request.Model);
        }
        catch (HttpRequestException ex) { return AiResult.Fail(ProviderId.Ollama, request.Model, AiErrorKind.Network, ex.GetType().Name); }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested) { return AiResult.Fail(ProviderId.Ollama, request.Model, AiErrorKind.Network, "timeout"); }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException) { return AiResult.Fail(ProviderId.Ollama, request.Model, AiErrorKind.Unknown, "resposta inesperada"); }
    }
}

public sealed class OllamaProvider : IAiProvider
{
    readonly OllamaClient _client;
    public OllamaProvider(OllamaClient client) { _client = client; }
    public ProviderId Id => ProviderId.Ollama;
    public bool IsExternal => false;

    public async Task<ProviderStatus> GetStatusAsync(CancellationToken ct)
    {
        var d = await _client.DiscoverAsync(ct).ConfigureAwait(false);
        return new ProviderStatus(d.Reachable && d.Models.Count > 0, d.Detail);
    }

    public Task<AiResult> CompleteAsync(AiRequest request, CancellationToken ct) => _client.ChatAsync(request, ct);
}
