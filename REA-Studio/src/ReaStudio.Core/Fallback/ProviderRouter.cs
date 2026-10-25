using ReaStudio.Core.Ai;
using ReaStudio.Core.Security;

namespace ReaStudio.Core.Fallback;

public sealed record FallbackPolicy(bool OnQuota = true, bool OnTemporary = true, bool OnNetwork = true,
    bool OnRecoverableAuth = false)
{
    /// <summary>Política e erro desconhecido/não suportado nunca provocam troca. Autenticação só se habilitado explicitamente.</summary>
    public bool ShouldFallback(AiErrorKind k) => k switch
    {
        AiErrorKind.QuotaExceeded => OnQuota,
        AiErrorKind.Temporary => OnTemporary,
        AiErrorKind.Network => OnNetwork,
        AiErrorKind.Authentication => OnRecoverableAuth,
        _ => false
    };
}

public sealed record RouteRequest(string TaskId, RoutingMode Mode, ProviderId Provider, string Model, string LocalModel,
    IReadOnlyList<AiMessage> Messages, IReadOnlyList<string> CompletedOperations, IReadOnlyList<string> EvidenceFiles);

public sealed record RouteOutcome(AiResult Result, bool FallbackUsed, bool MutationsNeedConfirmation,
    string? CheckpointPath, IReadOnlyList<AiResult> Attempts);

public sealed class ProviderRouter
{
    readonly Dictionary<ProviderId, IAiProvider> _providers;
    readonly FallbackPolicy _policy;
    readonly CheckpointStore _checkpoints;
    readonly StructuredLog? _log;

    public ProviderRouter(IEnumerable<IAiProvider> providers, FallbackPolicy policy, CheckpointStore checkpoints, StructuredLog? log = null)
    {
        _providers = providers.ToDictionary(p => p.Id);
        _policy = policy; _checkpoints = checkpoints; _log = log;
    }

    public async Task<RouteOutcome> RunAsync(RouteRequest r, CancellationToken ct)
    {
        _providers.TryGetValue(ProviderId.Ollama, out var local);

        if (r.Mode == RoutingMode.LocalOnly)
        {
            if (local is null) return Single(AiResult.Fail(ProviderId.Ollama, r.LocalModel, AiErrorKind.Unsupported, "Ollama não configurado"));
            return Single(await Call(local, r.LocalModel, r.Messages, ct));
        }

        if (!_providers.TryGetValue(r.Provider, out var primary))
            return Single(AiResult.Fail(r.Provider, r.Model, AiErrorKind.Unsupported, "provedor não registrado"));

        var first = await Call(primary, r.Model, r.Messages, ct);
        if (first.Success || r.Mode == RoutingMode.Manual || !primary.IsExternal || !_policy.ShouldFallback(first.Error))
            return Single(first);

        if (local is null)
            return new RouteOutcome(first, false, false, null, new[] { first });

        string path;
        try
        {
            path = _checkpoints.Save(new Checkpoint(r.TaskId, DateTime.UtcNow, r.Provider, r.Model, first.Error,
                r.Messages.ToList(), r.CompletedOperations.ToList(), CheckpointStore.Hash(r.EvidenceFiles)));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _log?.Write("error", "checkpoint_failed", new Dictionary<string, object?> { ["task"] = r.TaskId });
            return new RouteOutcome(first with { Detail = "falha ao salvar checkpoint; troca cancelada" }, false, false, null, new[] { first });
        }
        _log?.Write("warn", "fallback", new Dictionary<string, object?>
            { ["task"] = r.TaskId, ["from"] = r.Provider.ToString(), ["reason"] = first.Error.ToString(), ["checkpoint"] = path });

        var resumed = new List<AiMessage>(r.Messages)
        {
            new("system", "Retomada a partir de checkpoint após troca de provedor (" + first.Error + "). " +
                "Operações já executadas, NÃO repetir: " + (r.CompletedOperations.Count == 0 ? "(nenhuma)" : string.Join(", ", r.CompletedOperations)) +
                ". Não altere arquivos sem confirmação explícita do usuário.")
        };
        var second = await Call(local, r.LocalModel, resumed, ct);
        return new RouteOutcome(second, true, true, path, new[] { first, second });
    }

    async Task<AiResult> Call(IAiProvider p, string model, IReadOnlyList<AiMessage> msgs, CancellationToken ct)
    {
        var res = await p.CompleteAsync(new AiRequest(model, msgs), ct);
        _log?.Write(res.Success ? "info" : "warn", "result", new Dictionary<string, object?>
            { ["provider"] = res.Provider.ToString(), ["model"] = res.Model, ["ok"] = res.Success, ["error"] = res.Error.ToString() });
        return res;
    }

    static RouteOutcome Single(AiResult r) => new(r, false, false, null, new[] { r });
}
