namespace ReaStudio.Core.Ai;

/// <summary>
/// Sonda para Codex CLI / Claude Code instalados. Apenas detecta o executável no PATH.
/// A execução NÃO está implementada: a autenticação oficial permanece nas próprias ferramentas
/// e o Studio nunca lê tokens delas.
/// </summary>
public sealed class CliAgentProvider : IAiProvider
{
    readonly string _exe;
    readonly Func<string?> _pathProvider;
    public ProviderId Id { get; }
    public bool IsExternal => true;

    public CliAgentProvider(ProviderId id, string executable, Func<string?>? pathProvider = null)
    {
        Id = id; _exe = executable;
        _pathProvider = pathProvider ?? (() => Environment.GetEnvironmentVariable("PATH"));
    }

    public string? FindExecutable()
    {
        var exts = OperatingSystem.IsWindows() ? new[] { ".exe", ".cmd", ".bat", "" } : new[] { "" };
        foreach (var dir in (_pathProvider() ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            foreach (var ext in exts)
            {
                var candidate = Path.Combine(dir, _exe + ext);
                if (File.Exists(candidate)) return candidate;
            }
        return null;
    }

    public Task<ProviderStatus> GetStatusAsync(CancellationToken ct)
    {
        var path = FindExecutable();
        return Task.FromResult(path is null
            ? new ProviderStatus(false, $"'{_exe}' não encontrado no PATH")
            : new ProviderStatus(true, $"Detectado em {path}; execução pelo Studio ainda não implementada"));
    }

    public Task<AiResult> CompleteAsync(AiRequest request, CancellationToken ct)
        => Task.FromResult(AiResult.Fail(Id, request.Model, AiErrorKind.Unsupported,
            "Adaptador CLI ainda não implementado nesta fase"));
}
