using System.Diagnostics;
using System.Text.Json;

namespace ReaStudio.Core.Mcp;

public interface IMcpTransport : IAsyncDisposable
{
    Task SendAsync(string json, CancellationToken ct);
    Task<string?> ReceiveAsync(CancellationToken ct);
}

public sealed class McpException : Exception { public McpException(string m) : base(m) { } }

public sealed record McpTool(string Name, string? Description);

/// <summary>Cliente MCP mínimo (JSON-RPC por linha, stdio). Lista ferramentas; não presume suporte a nenhuma.</summary>
public sealed class McpClient
{
    readonly IMcpTransport _t;
    int _id;
    public string? ServerName { get; private set; }

    public McpClient(IMcpTransport transport) { _t = transport; }

    public async Task InitializeAsync(CancellationToken ct)
    {
        var res = await RequestAsync("initialize", new Dictionary<string, object?>
        {
            ["protocolVersion"] = "2024-11-05",
            ["capabilities"] = new Dictionary<string, object?>(),
            ["clientInfo"] = new { name = "rea-studio", version = "0.1.0" }
        }, ct);
        if (res.TryGetProperty("serverInfo", out var si) && si.TryGetProperty("name", out var n)) ServerName = n.GetString();
        await _t.SendAsync(JsonSerializer.Serialize(new { jsonrpc = "2.0", method = "notifications/initialized" }), ct);
    }

    public async Task<IReadOnlyList<McpTool>> ListToolsAsync(CancellationToken ct)
    {
        var tools = new List<McpTool>();
        string? cursor = null;
        do
        {
            var p = new Dictionary<string, object?>();
            if (cursor != null) p["cursor"] = cursor;
            var res = await RequestAsync("tools/list", p, ct);
            foreach (var t in res.GetProperty("tools").EnumerateArray())
                tools.Add(new McpTool(t.GetProperty("name").GetString() ?? "",
                    t.TryGetProperty("description", out var d) ? d.GetString() : null));
            cursor = res.TryGetProperty("nextCursor", out var c) ? c.GetString() : null;
        } while (cursor != null);
        return tools;
    }

    /// <summary>Chamada crua. A autorização (ToolAuthorizer) deve ser feita pelo chamador antes.</summary>
    public async Task<JsonElement> CallToolAsync(string name, IDictionary<string, object?> args, CancellationToken ct)
        => await RequestAsync("tools/call", new Dictionary<string, object?> { ["name"] = name, ["arguments"] = args }, ct);

    async Task<JsonElement> RequestAsync(string method, Dictionary<string, object?> p, CancellationToken ct)
    {
        var id = ++_id;
        var msg = new Dictionary<string, object?> { ["jsonrpc"] = "2.0", ["id"] = id, ["method"] = method, ["params"] = p };
        await _t.SendAsync(JsonSerializer.Serialize(msg), ct);
        while (true)
        {
            var line = await _t.ReceiveAsync(ct) ?? throw new McpException("Servidor MCP encerrou a conexão.");
            JsonDocument doc;
            try { doc = JsonDocument.Parse(line); } catch (JsonException) { continue; }
            using (doc)
            {
                var root = doc.RootElement;
                if (!root.TryGetProperty("id", out var rid) || rid.ValueKind != JsonValueKind.Number || rid.GetInt32() != id) continue;
                if (root.TryGetProperty("error", out var err))
                    throw new McpException(err.TryGetProperty("message", out var m) ? m.GetString() ?? "erro MCP" : "erro MCP");
                return root.GetProperty("result").Clone();
            }
        }
    }
}

public sealed class StdioMcpTransport : IMcpTransport
{
    readonly Process _p;

    public StdioMcpTransport(string command, IEnumerable<string> args)
    {
        var psi = new ProcessStartInfo(command)
        {
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            UseShellExecute = false, CreateNoWindow = true
        };
        foreach (var a in args) psi.ArgumentList.Add(a);
        _p = Process.Start(psi) ?? throw new McpException("Não foi possível iniciar o servidor MCP.");
        _p.ErrorDataReceived += (_, _) => { };
        _p.BeginErrorReadLine();
    }

    public async Task SendAsync(string json, CancellationToken ct)
    {
        await _p.StandardInput.WriteLineAsync(json.AsMemory(), ct);
        await _p.StandardInput.FlushAsync(ct);
    }

    public async Task<string?> ReceiveAsync(CancellationToken ct) => await _p.StandardOutput.ReadLineAsync(ct);

    public ValueTask DisposeAsync()
    {
        try { if (!_p.HasExited) _p.Kill(true); } catch (InvalidOperationException) { }
        _p.Dispose();
        return ValueTask.CompletedTask;
    }
}
