using System.Security.Cryptography;
using System.Text;

namespace ReaStudio.Core.Security;

public interface ICredentialStore
{
    void Save(string name, string secret);
    string? TryGet(string name);
    void Delete(string name);
}

public sealed class InMemoryCredentialStore : ICredentialStore
{
    readonly Dictionary<string, string> _d = new();
    public void Save(string name, string secret) => _d[name] = secret;
    public string? TryGet(string name) => _d.TryGetValue(name, out var v) ? v : null;
    public void Delete(string name) => _d.Remove(name);
}

/// <summary>Credenciais protegidas por DPAPI (escopo do usuário Windows). Nunca grava texto puro.</summary>
public sealed class DpapiCredentialStore : ICredentialStore
{
    static readonly byte[] Entropy = Encoding.UTF8.GetBytes("REA-Studio.v1");
    readonly string _dir;

    public DpapiCredentialStore(string? directory = null)
    {
        _dir = directory ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "REA-Studio", "credentials");
    }

    string PathFor(string name) => Path.Combine(_dir, Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(name)))[..16] + ".bin");

    public void Save(string name, string secret)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("DPAPI requer Windows.");
        Directory.CreateDirectory(_dir);
        File.WriteAllBytes(PathFor(name), ProtectedData.Protect(Encoding.UTF8.GetBytes(secret), Entropy, DataProtectionScope.CurrentUser));
    }

    public string? TryGet(string name)
    {
        if (!OperatingSystem.IsWindows()) return null;
        var p = PathFor(name);
        if (!File.Exists(p)) return null;
        try { return Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(p), Entropy, DataProtectionScope.CurrentUser)); }
        catch (CryptographicException) { return null; }
    }

    public void Delete(string name) { var p = PathFor(name); if (File.Exists(p)) File.Delete(p); }
}
