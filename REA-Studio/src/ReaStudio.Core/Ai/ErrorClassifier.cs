namespace ReaStudio.Core.Ai;

/// <summary>Classifica apenas erros realmente expostos pela integração; não infere créditos restantes.</summary>
public static class ErrorClassifier
{
    public static AiErrorKind FromHttp(int status, string? body)
    {
        var b = body ?? "";
        bool policy = b.Contains("policy", StringComparison.OrdinalIgnoreCase)
                      || b.Contains("content_filter", StringComparison.OrdinalIgnoreCase);
        if (status == 429) return AiErrorKind.QuotaExceeded;
        if (status is 401 or 403) return policy ? AiErrorKind.Policy : AiErrorKind.Authentication;
        if (status == 400 && policy) return AiErrorKind.Policy;
        if (status == 408 || status >= 500) return AiErrorKind.Temporary;
        return AiErrorKind.Unknown;
    }
}
