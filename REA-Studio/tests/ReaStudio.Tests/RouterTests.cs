using ReaStudio.Core.Ai;
using ReaStudio.Core.Fallback;
using ReaStudio.Core.Security;
using Xunit;

namespace ReaStudio.Tests;

public class RouterTests : IDisposable
{
    readonly string _dir = Path.Combine(Path.GetTempPath(), "rea-studio-tests-" + Guid.NewGuid().ToString("N"));
    public RouterTests() { Directory.CreateDirectory(_dir); }
    public void Dispose() { try { Directory.Delete(_dir, true); } catch (IOException) { } }

    ProviderRouter Router(FallbackPolicy? pol, params IAiProvider[] ps)
        => new(ps, pol ?? new FallbackPolicy(), new CheckpointStore(Path.Combine(_dir, "cp")));

    RouteRequest Req(RoutingMode mode, ProviderId p = ProviderId.OpenAiApi, string[]? files = null, string[]? done = null)
        => new("tarefa-1", mode, p, "gpt-x", "gpt-oss:20b", new[] { new AiMessage("user", "olá") },
               done ?? Array.Empty<string>(), files ?? Array.Empty<string>());

    [Fact]
    public async Task Manual_UsesSelectedProvider_AndNeverFallsBack()
    {
        var cloud = FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.QuotaExceeded);
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, cloud, local).RunAsync(Req(RoutingMode.Manual), default);
        Assert.False(o.Result.Success);
        Assert.False(o.FallbackUsed);
        Assert.Equal(0, local.Calls);
    }

    [Fact]
    public async Task LocalOnly_NeverCallsExternalProvider()
    {
        var cloud = FakeProvider.Ok(ProviderId.OpenAiApi, true);
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, cloud, local).RunAsync(Req(RoutingMode.LocalOnly), default);
        Assert.Equal(0, cloud.Calls);
        Assert.Equal(ProviderId.Ollama, o.Result.Provider);
        Assert.Equal("gpt-oss:20b", o.Result.Model);
    }

    [Fact]
    public async Task Automatic_PrimarySuccess_NoFallback()
    {
        var cloud = FakeProvider.Ok(ProviderId.OpenAiApi, true);
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, cloud, local).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.True(o.Result.Success);
        Assert.False(o.FallbackUsed);
        Assert.Equal(0, local.Calls);
        Assert.Equal(ProviderId.OpenAiApi, o.Result.Provider);
    }

    [Theory]
    [InlineData(AiErrorKind.QuotaExceeded)]
    [InlineData(AiErrorKind.Temporary)]
    [InlineData(AiErrorKind.Network)]
    public async Task Automatic_FallsBackToOllama_OnRecoverableErrors(AiErrorKind kind)
    {
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, FakeProvider.Failing(ProviderId.OpenAiApi, kind), local).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.True(o.FallbackUsed);
        Assert.True(o.MutationsNeedConfirmation);
        Assert.Equal(ProviderId.Ollama, o.Result.Provider);
        Assert.Equal(2, o.Attempts.Count);
    }

    [Theory]
    [InlineData(AiErrorKind.Authentication)]
    [InlineData(AiErrorKind.Policy)]
    [InlineData(AiErrorKind.Unknown)]
    public async Task Automatic_DoesNotFallBack_OnAuthPolicyOrUnknown(AiErrorKind kind)
    {
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, FakeProvider.Failing(ProviderId.OpenAiApi, kind), local).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.False(o.FallbackUsed);
        Assert.Equal(0, local.Calls);
    }

    [Fact]
    public async Task Authentication_FallsBack_OnlyWhenPolicyAllows_ButPolicyNever()
    {
        var pol = new FallbackPolicy(OnRecoverableAuth: true);
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(pol, FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.Authentication), local).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.True(o.FallbackUsed);
        var local2 = FakeProvider.Ok(ProviderId.Ollama, false);
        var o2 = await Router(pol, FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.Policy), local2).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.False(o2.FallbackUsed);
    }

    [Fact]
    public async Task Simulated429_FromRealOpenAiAdapter_TriggersCheckpointThenFallback()
    {
        var store = new InMemoryCredentialStore();
        store.Save(OpenAiApiProvider.Credential, "sk-TESTE-NAO-REAL-123456");
        var http = new HttpClient(new FakeHttpHandler(_ => FakeHttpHandler.Json("{\"error\":{\"type\":\"insufficient_quota\"}}", (System.Net.HttpStatusCode)429)));
        var openai = new OpenAiApiProvider(http, store);
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, openai, local).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.Equal(AiErrorKind.QuotaExceeded, o.Attempts[0].Error);
        Assert.NotNull(o.CheckpointPath);
        Assert.True(File.Exists(o.CheckpointPath));
        Assert.Equal(ProviderId.Ollama, o.Result.Provider);
    }

    [Fact]
    public async Task Fallback_Checkpoint_ResumeCarriesCompletedOperations_AndForbidsRepeat()
    {
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.QuotaExceeded), local)
            .RunAsync(Req(RoutingMode.Automatic, done: new[] { "op-apagar-7" }), default);
        var sys = local.Requests[0].Messages.Last();
        Assert.Equal("system", sys.Role);
        Assert.Contains("op-apagar-7", sys.Content);
        Assert.Contains("NÃO repetir", sys.Content);
        var cp = new CheckpointStore(Path.Combine(_dir, "cp")).Load("tarefa-1");
        Assert.NotNull(cp);
        Assert.Contains("op-apagar-7", cp!.CompletedOperations);
        Assert.Equal(AiErrorKind.QuotaExceeded, cp.Reason);
        Assert.Equal(ProviderId.OpenAiApi, cp.FromProvider);
    }

    [Fact]
    public async Task Fallback_PreservesFiles_AndVerifyDetectsLaterChange()
    {
        var f = Path.Combine(_dir, "alvo.exe");
        var bytes = new byte[] { 1, 2, 3, 4 };
        File.WriteAllBytes(f, bytes);
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        await Router(null, FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.Temporary), local)
            .RunAsync(Req(RoutingMode.Automatic, files: new[] { f }), default);
        Assert.Equal(bytes, File.ReadAllBytes(f));
        var cp = new CheckpointStore(Path.Combine(_dir, "cp")).Load("tarefa-1")!;
        Assert.Empty(CheckpointStore.Verify(cp));
        File.WriteAllBytes(f, new byte[] { 9 });
        Assert.Single(CheckpointStore.Verify(cp));
        File.Delete(f);
        Assert.Contains("ausente", CheckpointStore.Verify(cp)[0]);
    }

    [Fact]
    public async Task CheckpointFailure_CancelsSwitch()
    {
        var blocker = Path.Combine(_dir, "arquivo-no-lugar-de-pasta");
        File.WriteAllText(blocker, "x");
        var router = new ProviderRouter(new IAiProvider[] { FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.QuotaExceeded), FakeProvider.Ok(ProviderId.Ollama, false) },
            new FallbackPolicy(), new CheckpointStore(Path.Combine(blocker, "cp")));
        var o = await router.RunAsync(Req(RoutingMode.Automatic), default);
        Assert.False(o.FallbackUsed);
        Assert.False(o.Result.Success);
    }

    [Fact]
    public async Task NoSwitch_WhenOllamaNotRegistered()
    {
        var o = await Router(null, FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.QuotaExceeded)).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.False(o.FallbackUsed);
        Assert.False(o.Result.Success);
    }

    [Fact]
    public async Task EachResult_RecordsProducingModel()
    {
        var local = FakeProvider.Ok(ProviderId.Ollama, false);
        var o = await Router(null, FakeProvider.Failing(ProviderId.OpenAiApi, AiErrorKind.QuotaExceeded), local).RunAsync(Req(RoutingMode.Automatic), default);
        Assert.Equal(("gpt-x", ProviderId.OpenAiApi), (o.Attempts[0].Model, o.Attempts[0].Provider));
        Assert.Equal(("gpt-oss:20b", ProviderId.Ollama), (o.Attempts[1].Model, o.Attempts[1].Provider));
    }
}
