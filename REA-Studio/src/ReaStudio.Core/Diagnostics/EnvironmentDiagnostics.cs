using ReaStudio.Core.Ai;
using ReaStudio.Core.Mcp;

namespace ReaStudio.Core.Diagnostics;

public enum DiagStatus { Ok, Warning, Failed }

public sealed record DiagItem(string Component, DiagStatus Status, string Detail);

/// <summary>Diagnóstico somente-leitura. "Ok" significa apenas o que foi realmente observado.</summary>
public static class EnvironmentDiagnostics
{
    public static async Task<IReadOnlyList<DiagItem>> RunAsync(OllamaClient ollama, IEnumerable<string>? mcpPaths, CancellationToken ct)
    {
        var items = new List<DiagItem>();

        var servers = McpRegistryInspector.ReadAll(mcpPaths);
        var rea = servers.Where(s => s.Name.Contains("rea", StringComparison.OrdinalIgnoreCase)).ToList();
        items.Add(servers.Count == 0
            ? new DiagItem("REA (registro MCP)", DiagStatus.Failed, "Nenhum servidor MCP encontrado nos registros conhecidos")
            : rea.Count == 0
                ? new DiagItem("REA (registro MCP)", DiagStatus.Warning, $"{servers.Count} servidor(es) MCP, nenhum chamado 'rea'")
                : new DiagItem("REA (registro MCP)", DiagStatus.Ok, $"Registrado: {rea[0].Name} (ferramentas ainda não verificadas)"));

        items.Add(FindGhidra());

        var d = await ollama.DiscoverAsync(ct);
        items.Add(!d.Reachable ? new DiagItem("Ollama", DiagStatus.Failed, d.Detail)
            : d.Models.Count == 0 ? new DiagItem("Ollama", DiagStatus.Warning, "Ativo, sem modelos instalados")
            : new DiagItem("Ollama", DiagStatus.Ok, d.Detail + (d.Models.Any(m => m.Name == OllamaClient.PreferredModel)
                ? $"; {OllamaClient.PreferredModel} disponível" : $"; {OllamaClient.PreferredModel} não instalado")));
        return items;
    }

    static DiagItem FindGhidra()
    {
        var env = Environment.GetEnvironmentVariable("GHIDRA_INSTALL_DIR");
        var roots = new List<string>();
        if (!string.IsNullOrWhiteSpace(env)) roots.Add(env);
        foreach (var b in new[] { @"C:\Ghidra", @"C:\Tools", @"C:\Program Files" })
            if (Directory.Exists(b))
                try { roots.AddRange(Directory.EnumerateDirectories(b, "ghidra*")); } catch (UnauthorizedAccessException) { }
        var hit = roots.FirstOrDefault(r => File.Exists(Path.Combine(r, "ghidraRun.bat")) || File.Exists(Path.Combine(r, "ghidraRun")));
        return hit != null ? new DiagItem("Ghidra", DiagStatus.Ok, "Instalação encontrada em " + hit + " (não executada)")
            : new DiagItem("Ghidra", DiagStatus.Failed, "Instalação não encontrada (defina GHIDRA_INSTALL_DIR)");
    }
}
