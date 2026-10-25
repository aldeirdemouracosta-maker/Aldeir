using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using ReaStudio.Core.Ai;

namespace ReaStudio.Core.Fallback;

public sealed record EvidenceFile(string Path, string? Sha256);

public sealed record Checkpoint(string TaskId, DateTime CreatedUtc, ProviderId FromProvider, string FromModel,
    AiErrorKind Reason, List<AiMessage> Messages, List<string> CompletedOperations, List<EvidenceFile> Evidence);

/// <summary>Grava checkpoints de forma atômica. Só guarda caminhos e hashes de arquivos: nunca os altera.</summary>
public sealed class CheckpointStore
{
    static readonly JsonSerializerOptions Json = new() { WriteIndented = true, Converters = { new JsonStringEnumConverter() } };
    readonly string _dir;

    public CheckpointStore(string directory) { _dir = directory; }

    string PathFor(string taskId) => Path.Combine(_dir, SafeName(taskId) + ".checkpoint.json");
    static string SafeName(string s) => string.Concat(s.Select(c => char.IsLetterOrDigit(c) || c is '-' or '_' ? c : '_'));

    public static List<EvidenceFile> Hash(IEnumerable<string> files)
        => files.Select(f => new EvidenceFile(f, File.Exists(f) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(f))) : null)).ToList();

    public string Save(Checkpoint cp)
    {
        Directory.CreateDirectory(_dir);
        var path = PathFor(cp.TaskId);
        var tmp = path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(cp, Json));
        File.Move(tmp, path, overwrite: true);
        return path;
    }

    public Checkpoint? Load(string taskId)
    {
        var p = PathFor(taskId);
        return File.Exists(p) ? JsonSerializer.Deserialize<Checkpoint>(File.ReadAllText(p), Json) : null;
    }

    /// <summary>Lista evidências ausentes ou alteradas desde o checkpoint (vazia = tudo preservado).</summary>
    public static IReadOnlyList<string> Verify(Checkpoint cp)
    {
        var problems = new List<string>();
        foreach (var e in cp.Evidence)
        {
            if (!File.Exists(e.Path)) { if (e.Sha256 != null) problems.Add($"ausente: {e.Path}"); continue; }
            var now = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(e.Path)));
            if (now != e.Sha256) problems.Add($"alterado: {e.Path}");
        }
        return problems;
    }
}
