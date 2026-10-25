using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using ReaStudio.Core.Security;

namespace ReaStudio.Core.Ai;

/// <summary>Base comum: envio HTTP com classificação de erro. Corpo de erro nunca vai para Detail.</summary>
public abstract class HttpApiProvider : IAiProvider
{
    protected readonly HttpClient Http;
    protected readonly ICredentialStore Credentials;
    protected readonly Uri Endpoint;
    protected abstract string CredentialName { get; }
    protected abstract string DisplayName { get; }

    public abstract ProviderId Id { get; }
    public bool IsExternal => true;

    protected HttpApiProvider(HttpClient http, ICredentialStore credentials, Uri endpoint)
    {
        Http = http; Credentials = credentials; Endpoint = endpoint;
    }

    protected abstract HttpRequestMessage BuildRequest(AiRequest request, string key);
    protected abstract string ParseText(JsonElement root);

    public Task<ProviderStatus> GetStatusAsync(CancellationToken ct)
        => Task.FromResult(Credentials.TryGet(CredentialName) is null
            ? new ProviderStatus(false, $"Chave de API {DisplayName} não configurada")
            : new ProviderStatus(true, "Chave configurada (validade não verificada)"));

    public async Task<AiResult> CompleteAsync(AiRequest request, CancellationToken ct)
    {
        var key = Credentials.TryGet(CredentialName);
        if (key is null)
            return AiResult.Fail(Id, request.Model, AiErrorKind.Authentication, $"Chave de API {DisplayName} não configurada");
        try
        {
            using var req = BuildRequest(request, key);
            using var resp = await Http.SendAsync(req, ct).ConfigureAwait(false);
            var body = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            if (!resp.IsSuccessStatusCode)
                return AiResult.Fail(Id, request.Model, ErrorClassifier.FromHttp((int)resp.StatusCode, body), $"HTTP {(int)resp.StatusCode}");
            using var doc = JsonDocument.Parse(body);
            return new AiResult(true, ParseText(doc.RootElement), Id, request.Model);
        }
        catch (HttpRequestException ex)
        {
            return AiResult.Fail(Id, request.Model, AiErrorKind.Network, ex.GetType().Name);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return AiResult.Fail(Id, request.Model, AiErrorKind.Network, "timeout");
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or IndexOutOfRangeException)
        {
            return AiResult.Fail(Id, request.Model, AiErrorKind.Unknown, "resposta inesperada");
        }
    }
}

public sealed class OpenAiApiProvider : HttpApiProvider
{
    public const string Credential = "openai";
    protected override string CredentialName => Credential;
    protected override string DisplayName => "OpenAI";
    public override ProviderId Id => ProviderId.OpenAiApi;

    public OpenAiApiProvider(HttpClient http, ICredentialStore credentials, Uri? endpoint = null)
        : base(http, credentials, endpoint ?? new Uri("https://api.openai.com/v1/chat/completions")) { }

    protected override HttpRequestMessage BuildRequest(AiRequest request, string key)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, Endpoint)
        {
            Content = JsonContent.Create(new
            {
                model = request.Model,
                messages = request.Messages.Select(m => new { role = m.Role, content = m.Content })
            })
        };
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key);
        return req;
    }

    protected override string ParseText(JsonElement root)
        => root.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString() ?? "";
}

public sealed class AnthropicApiProvider : HttpApiProvider
{
    public const string Credential = "anthropic";
    protected override string CredentialName => Credential;
    protected override string DisplayName => "Anthropic";
    public override ProviderId Id => ProviderId.AnthropicApi;

    public AnthropicApiProvider(HttpClient http, ICredentialStore credentials, Uri? endpoint = null)
        : base(http, credentials, endpoint ?? new Uri("https://api.anthropic.com/v1/messages")) { }

    protected override HttpRequestMessage BuildRequest(AiRequest request, string key)
    {
        var system = string.Join("\n", request.Messages.Where(m => m.Role == "system").Select(m => m.Content));
        var body = new Dictionary<string, object?>
        {
            ["model"] = request.Model,
            ["max_tokens"] = 4096,
            ["messages"] = request.Messages.Where(m => m.Role != "system")
                .Select(m => new { role = m.Role, content = m.Content }).ToList()
        };
        if (system.Length > 0) body["system"] = system;
        var req = new HttpRequestMessage(HttpMethod.Post, Endpoint) { Content = JsonContent.Create(body) };
        req.Headers.Add("x-api-key", key);
        req.Headers.Add("anthropic-version", "2023-06-01");
        return req;
    }

    protected override string ParseText(JsonElement root)
        => root.GetProperty("content")[0].GetProperty("text").GetString() ?? "";
}
