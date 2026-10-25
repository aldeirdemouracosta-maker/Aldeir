namespace ReaStudio.Core.Ai;

public enum ProviderId { Codex, OpenAiApi, ClaudeCode, AnthropicApi, Ollama }

public enum RoutingMode { Manual, Automatic, LocalOnly }

public enum AiErrorKind { None, QuotaExceeded, Temporary, Authentication, Network, Policy, Unsupported, Unknown }

public sealed record AiMessage(string Role, string Content);

public sealed record AiRequest(string Model, IReadOnlyList<AiMessage> Messages);

public sealed record AiResult(bool Success, string Text, ProviderId Provider, string Model,
    AiErrorKind Error = AiErrorKind.None, string? Detail = null)
{
    public static AiResult Fail(ProviderId provider, string model, AiErrorKind kind, string? detail = null)
        => new(false, "", provider, model, kind, detail);
}

public sealed record ProviderStatus(bool Available, string Detail);

public interface IAiProvider
{
    ProviderId Id { get; }
    bool IsExternal { get; }
    Task<ProviderStatus> GetStatusAsync(CancellationToken ct);
    Task<AiResult> CompleteAsync(AiRequest request, CancellationToken ct);
}
