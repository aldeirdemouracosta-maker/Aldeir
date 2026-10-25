using System.Net;
using ReaStudio.Core.Ai;
using ReaStudio.Core.Security;
using Xunit;

namespace ReaStudio.Tests;

public class ProviderAdapterTests
{
    static AiRequest Req() => new("m", new[] { new AiMessage("user", "oi") });
    static InMemoryCredentialStore Keys() { var s = new InMemoryCredentialStore(); s.Save("openai", "sk-TESTE-1234567890"); s.Save("anthropic", "sk-ant-TESTE-1234567890"); return s; }

    [Theory]
    [InlineData(429, AiErrorKind.QuotaExceeded)]
    [InlineData(503, AiErrorKind.Temporary)]
    [InlineData(529, AiErrorKind.Temporary)]
    [InlineData(401, AiErrorKind.Authentication)]
    [InlineData(403, AiErrorKind.Authentication)]
    public async Task OpenAi_ClassifiesHttpErrors(int code, AiErrorKind expected)
    {
        var p = new OpenAiApiProvider(new HttpClient(new FakeHttpHandler(_ => FakeHttpHandler.Json("{}", (HttpStatusCode)code))), Keys());
        var r = await p.CompleteAsync(Req(), default);
        Assert.Equal(expected, r.Error);
    }

    [Fact]
    public async Task PolicyBody_IsClassifiedAsPolicy()
    {
        var p = new OpenAiApiProvider(new HttpClient(new FakeHttpHandler(_ => FakeHttpHandler.Json("{\"error\":\"content_policy\"}", HttpStatusCode.BadRequest))), Keys());
        Assert.Equal(AiErrorKind.Policy, (await p.CompleteAsync(Req(), default)).Error);
    }

    [Fact]
    public async Task OpenAi_ParsesSuccess_AndSendsBearerKey()
    {
        string? auth = null;
        var h = new FakeHttpHandler(r => { auth = r.Headers.Authorization?.ToString(); return FakeHttpHandler.Json("{\"choices\":[{\"message\":{\"content\":\"resposta\"}}]}"); });
        var r = await new OpenAiApiProvider(new HttpClient(h), Keys()).CompleteAsync(Req(), default);
        Assert.True(r.Success);
        Assert.Equal("resposta", r.Text);
        Assert.StartsWith("Bearer sk-", auth);
    }

    [Fact]
    public async Task Anthropic_ParsesSuccess()
    {
        var h = new FakeHttpHandler(r => FakeHttpHandler.Json("{\"content\":[{\"type\":\"text\",\"text\":\"claude diz\"}]}"));
        var r = await new AnthropicApiProvider(new HttpClient(h), Keys()).CompleteAsync(Req(), default);
        Assert.Equal("claude diz", r.Text);
        Assert.Equal(ProviderId.AnthropicApi, r.Provider);
    }

    [Fact]
    public async Task MissingKey_IsAuthenticationError_WithoutNetworkCall()
    {
        var h = new FakeHttpHandler(_ => throw new InvalidOperationException("não deveria chamar"));
        var r = await new OpenAiApiProvider(new HttpClient(h), new InMemoryCredentialStore()).CompleteAsync(Req(), default);
        Assert.Equal(AiErrorKind.Authentication, r.Error);
        Assert.Empty(h.Paths);
    }

    [Fact]
    public async Task ConnectionFailure_IsNetworkError()
    {
        var r = await new OpenAiApiProvider(new HttpClient(new ThrowingHandler()), Keys()).CompleteAsync(Req(), default);
        Assert.Equal(AiErrorKind.Network, r.Error);
    }

    [Fact]
    public async Task CliProbe_ReportsMissingExecutable_AndDoesNotPretendToRun()
    {
        var p = new CliAgentProvider(ProviderId.Codex, "codex-inexistente", () => Path.GetTempPath());
        Assert.False((await p.GetStatusAsync(default)).Available);
        Assert.Equal(AiErrorKind.Unsupported, (await p.CompleteAsync(Req(), default)).Error);
    }
}
