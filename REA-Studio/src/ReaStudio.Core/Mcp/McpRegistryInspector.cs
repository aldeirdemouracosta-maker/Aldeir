using System.Text.Json;
using System.Text.RegularExpressions;

namespace ReaStudio.Core.Mcp;

/// <summary>Variáveis de ambiente (env) são descartadas de propósito: podem conter segredos.</summary>
public sealed record McpServerEntry(string Name, string? Command, IReadOnlyList<string> Args, string Source);

/// <summary>Leitura somente-leitura de registros MCP existentes (Codex config.toml, JSON estilo Claude). Nunca grava.</summary>
public static class McpRegistryInspector
{
    public static IEnumerable<string> DefaultCandidatePaths()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        yield return Path.Combine(home, ".codex", "config.toml");
        yield return Path.Combine(appData, "Claude", "claude_desktop_config.json");
        yield return Path.Combine(home, ".claude.json");
    }

    public static IReadOnlyList<McpServerEntry> ReadAll(IEnumerable<string>? paths = null)
    {
        var all = new List<McpServerEntry>();
        foreach (var p in paths ?? DefaultCandidatePaths())
        {
            if (!File.Exists(p)) continue;
            string text;
            using (var fs = new FileStream(p, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs)) text = sr.ReadToEnd();
            try
            {
                all.AddRange(p.EndsWith(".toml", StringComparison.OrdinalIgnoreCase) ? ParseToml(text, p) : ParseJson(text, p));
            }
            catch (JsonException) { }
        }
        return all;
    }

    public static IReadOnlyList<McpServerEntry> ParseToml(string text, string source)
    {
        var list = new List<McpServerEntry>();
        string? name = null, cmd = null; var args = new List<string>();
        void Flush() { if (name != null) list.Add(new McpServerEntry(name, cmd, args.ToList(), source)); name = null; cmd = null; args.Clear(); }
        foreach (var raw in text.Split('\n'))
        {
            var line = raw.Trim();
            var h = Regex.Match(line, @"^\[mcp_servers\.([^\].]+)\]$");
            if (h.Success) { Flush(); name = h.Groups[1].Value.Trim('"'); continue; }
            if (line.StartsWith('[')) { Flush(); continue; }
            if (name == null) continue;
            var c = Regex.Match(line, "^command\\s*=\\s*\"(.*)\"");
            if (c.Success) cmd = c.Groups[1].Value.Replace("\\\\", "\\");
            var a = Regex.Match(line, @"^args\s*=\s*\[(.*)\]");
            if (a.Success) foreach (Match s in Regex.Matches(a.Groups[1].Value, "\"((?:[^\"\\\\]|\\\\.)*)\"")) args.Add(s.Groups[1].Value.Replace("\\\\", "\\"));
        }
        Flush();
        return list;
    }

    public static IReadOnlyList<McpServerEntry> ParseJson(string text, string source)
    {
        var list = new List<McpServerEntry>();
        using var doc = JsonDocument.Parse(text);
        if (!doc.RootElement.TryGetProperty("mcpServers", out var servers) || servers.ValueKind != JsonValueKind.Object) return list;
        foreach (var s in servers.EnumerateObject())
        {
            var cmd = s.Value.TryGetProperty("command", out var c) ? c.GetString() : null;
            var args = s.Value.TryGetProperty("args", out var a) && a.ValueKind == JsonValueKind.Array
                ? a.EnumerateArray().Select(x => x.GetString() ?? "").ToList() : new List<string>();
            list.Add(new McpServerEntry(s.Name, cmd, args, source));
        }
        return list;
    }
}
