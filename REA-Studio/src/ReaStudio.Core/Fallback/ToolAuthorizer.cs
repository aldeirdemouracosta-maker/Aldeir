namespace ReaStudio.Core.Fallback;

public enum ToolRisk { ReadOnly, Mutating, Destructive }

public sealed record ToolCall(string OperationId, string Name);

public sealed record AuthContext(bool UserConfirmed, bool ProviderSwitched, ISet<string> CompletedOperations);

public sealed record AuthDecision(bool Allowed, string Reason);

/// <summary>
/// Somente ferramentas explicitamente marcadas como somente-leitura passam sem confirmação.
/// Ferramentas desconhecidas contam como Mutating (não se presume segurança de uma ferramenta MCP não testada).
/// </summary>
public sealed class ToolAuthorizer
{
    readonly Dictionary<string, ToolRisk> _risks;
    public ToolAuthorizer(IDictionary<string, ToolRisk>? risks = null) { _risks = new(risks ?? new Dictionary<string, ToolRisk>()); }

    public ToolRisk RiskOf(string tool) => _risks.TryGetValue(tool, out var r) ? r : ToolRisk.Mutating;

    public AuthDecision Authorize(ToolCall call, AuthContext ctx)
    {
        var risk = RiskOf(call.Name);
        if (risk == ToolRisk.ReadOnly) return new(true, "somente leitura");
        if (ctx.CompletedOperations.Contains(call.OperationId))
            return new(false, "operação já executada antes da troca de provedor; não será repetida");
        if (!ctx.UserConfirmed)
            return new(false, ctx.ProviderSwitched
                ? "provedor foi trocado: nova confirmação do usuário é obrigatória"
                : "operação que altera arquivos exige confirmação do usuário");
        return new(true, "confirmada pelo usuário");
    }
}
