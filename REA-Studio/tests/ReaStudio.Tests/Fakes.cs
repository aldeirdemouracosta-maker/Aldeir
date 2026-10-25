using System.Net;
using System.Text;
using ReaStudio.Core.Ai;
using ReaStudio.Core.Mcp;

namespace ReaStudio.Tests;

/// <summary>Provedor simulado: nunca acessa rede nem consome créditos.</summary>
public sealed class FakeProvider : IAiProvider
{
    readonly Func<AiRequest, AiResult> _respond;
    public int Calls { get; private set; }
    public List<AiRequest> Requests { get; } = new();
    public ProviderId Id { get; }
    public bool IsExternal { get; }

    public FakeProvider(ProviderId id, bool external, Func<AiRequest, AiResult> respond)
    { Id = id; IsExternal = external; _respond = respond; }

    public Task<ProviderStatus> GetStatusAsync(CancellationToken ct) => Task.FromResult(new ProviderStatus(true, "fake"));
    public Task<AiResult> CompleteAsync(AiRequest r, CancellationToken ct) { Calls++; Requests.Add(r); return Task.FromResult(_respond(r)); }

    public static FakeProvider Ok(ProviderId id, bool external) => new(id, external, r => new AiResult(true, "ok:" + id, id, r.Model));
    public static FakeProvider Failing(ProviderId id, AiErrorKind k) => new(id, true, r => AiResult.Fail(id, r.Model, k, "simulado"));
}

public sealed class FakeHttpHandler : HttpMessageHandler
{
    readonly Func<HttpRequestMessage, HttpResponseMessage> _h;
    public List<string> Paths { get; } = new();
    public FakeHttpHandler(Func<HttpRequestMessage, HttpResponseMessage> h) { _h = h; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    { Paths.Add(request.RequestUri!.AbsolutePath); return Task.FromResult(_h(request)); }

    public static HttpResponseMessage Json(string json, HttpStatusCode code = HttpStatusCode.OK)
        => new(code) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
}

public sealed class ThrowingHandler : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        => throw new HttpRequestException("connection refused");
}

/// <summary>Servidor MCP em memória que responde initialize e tools/list.</summary>
public sealed class FakeMcpTransport : IMcpTransport
{
    readonly Queue<string> _out = new();
    public List<string> Sent { get; } = new();

    public Task SendAsync(string json, CancellationToken ct)
    {
        Sent.Add(json);
        using var doc = System.Text.Json.JsonDocument.Parse(json);
        var root = doc.RootElement;
        if (!root.TryGetProperty("id", out var id)) return Task.CompletedTask;
        var method = root.GetProperty("method").GetString();
        _out.Enqueue("not json noise");
        _out.Enqueue("{\"jsonrpc\":\"2.0\",\"method\":\"notifications/message\"}");
        _out.Enqueue(method switch
        {
            "initialize" => $"{{\"jsonrpc\":\"2.0\",\"id\":{id},\"result\":{{\"serverInfo\":{{\"name\":\"fake-rea\"}}}}}}",
            "tools/list" => $"{{\"jsonrpc\":\"2.0\",\"id\":{id},\"result\":{{\"tools\":[{{\"name\":\"list_functions\",\"description\":\"d\"}},{{\"name\":\"rename\"}}]}}}}",
            _ => $"{{\"jsonrpc\":\"2.0\",\"id\":{id},\"error\":{{\"code\":-32601,\"message\":\"nao suportado\"}}}}"
        });
        return Task.CompletedTask;
    }

    public Task<string?> ReceiveAsync(CancellationToken ct) => Task.FromResult(_out.Count > 0 ? _out.Dequeue() : null);
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}
