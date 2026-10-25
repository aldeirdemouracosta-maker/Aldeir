using System.Text.Json;
using System.Text.RegularExpressions;

namespace ReaStudio.Core.Security;

/// <summary>Log JSON Lines com redação de segredos (chaves sk-..., Bearer ..., campos sensíveis).</summary>
public sealed class StructuredLog
{
    static readonly Regex Secret = new(@"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+)", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    static readonly string[] SensitiveKeys = { "key", "token", "secret", "authorization", "password", "senha" };
    readonly string _path;
    readonly object _lock = new();

    public StructuredLog(string path)
    {
        _path = path;
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
    }

    public static string Redact(string s) => Secret.Replace(s, "[REDACTED]");

    public void Write(string level, string evt, IDictionary<string, object?>? fields = null)
    {
        var row = new Dictionary<string, object?> { ["ts"] = DateTime.UtcNow.ToString("O"), ["level"] = level, ["event"] = evt };
        if (fields != null)
            foreach (var (k, v) in fields)
                row[k] = SensitiveKeys.Any(s => k.Contains(s, StringComparison.OrdinalIgnoreCase))
                    ? "[REDACTED]" : v is string str ? Redact(str) : v;
        var line = Redact(JsonSerializer.Serialize(row));
        lock (_lock) File.AppendAllText(_path, line + Environment.NewLine);
    }
}
