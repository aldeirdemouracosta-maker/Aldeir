using ReaStudio.Core.Ai;
using Xunit;

namespace ReaStudio.Tests;

public class OllamaTests
{
    const string Tags = "{\"models\":[{\"name\":\"llama3:8b\",\"size\":4000000000,\"details\":{\"parameter_size\":\"8B\",\"quantization_level\":\"Q4_0\"}},{\"name\":\"gpt-oss:20b\",\"size\":13000000000,\"details\":{\"parameter_size\":\"20B\",\"quantization_level\":\"MXFP4\"}}]}";

    static HttpResponseMessage Route(HttpRequestMessage r) => r.RequestUri!.AbsolutePath switch
    {
        "/api/tags" => FakeHttpHandler.Json(Tags),
        "/api/ps" => FakeHttpHandler.Json("{\"models\":[{\"name\":\"gpt-oss:20b\"}]}"),
        "/api/show" => r.Content!.ReadAsStringAsync().Result.Contains("gpt-oss")
            ? FakeHttpHandler.Json("{\"model_info\":{\"gptoss.context_length\":131072},\"parameters\":\"num_ctx 8192\\nstop x\",\"capabilities\":[\"completion\",\"tools\"]}")
            : FakeHttpHandler.Json("{\"model_info\":{\"llama.context_length\":8192},\"capabilities\":[\"completion\"]}"),
        "/api/chat" => FakeHttpHandler.Json("{\"message\":{\"role\":\"assistant\",\"content\":\"local\"}}"),
        _ => FakeHttpHandler.Json("{}", System.Net.HttpStatusCode.NotFound)
    };

    [Fact]
    public async Task Discovers_OnlyInstalledModels_WithRealMetadata()
    {
        var d = await new OllamaClient(new HttpClient(new FakeHttpHandler(Route))).DiscoverAsync(default);
        Assert.True(d.Reachable);
        Assert.Equal(2, d.Models.Count);
        var g = d.Models.Single(m => m.Name == "gpt-oss:20b");
        Assert.Equal(131072, g.MaxContext);
        Assert.Equal(8192, g.ConfiguredContext);
        Assert.Equal(ToolSupport.Declared, g.Tools);
        Assert.True(g.LoadedNow);
        Assert.Equal((long)(13000000000 * 1.2), g.EstimatedMemoryBytes);
        var l = d.Models.Single(m => m.Name == "llama3:8b");
        Assert.Equal(ToolSupport.NotDeclared, l.Tools);
        Assert.Null(l.ConfiguredContext);
        Assert.False(l.LoadedNow);
    }

    [Fact]
    public async Task Prefers_GptOss20b_WhenInstalled_ElseToolCapable_ElseFirst()
    {
        var d = await new OllamaClient(new HttpClient(new FakeHttpHandler(Route))).DiscoverAsync(default);
        Assert.Equal("gpt-oss:20b", OllamaClient.SelectPreferred(d.Models)!.Name);
        var without = d.Models.Where(m => m.Name != "gpt-oss:20b").ToList();
        Assert.Equal("llama3:8b", OllamaClient.SelectPreferred(without)!.Name);
        Assert.Null(OllamaClient.SelectPreferred(Array.Empty<OllamaModelInfo>()));
    }

    [Fact]
    public async Task ConnectionFailure_ReportsUnreachable_WithoutThrowing()
    {
        var d = await new OllamaClient(new HttpClient(new ThrowingHandler())).DiscoverAsync(default);
        Assert.False(d.Reachable);
        Assert.Empty(d.Models);
        var p = new OllamaProvider(new OllamaClient(new HttpClient(new ThrowingHandler())));
        Assert.False((await p.GetStatusAsync(default)).Available);
        Assert.Equal(AiErrorKind.Network, (await p.CompleteAsync(new AiRequest("m", Array.Empty<AiMessage>()), default)).Error);
    }

    [Fact]
    public async Task Chat_ReturnsTextAndModel()
    {
        var r = await new OllamaProvider(new OllamaClient(new HttpClient(new FakeHttpHandler(Route))))
            .CompleteAsync(new AiRequest("gpt-oss:20b", new[] { new AiMessage("user", "oi") }), default);
        Assert.True(r.Success);
        Assert.Equal("local", r.Text);
        Assert.Equal(ProviderId.Ollama, r.Provider);
    }

    [Fact]
    public void OllamaIsNotExternal() => Assert.False(new OllamaProvider(new OllamaClient(new HttpClient())).IsExternal);
}
