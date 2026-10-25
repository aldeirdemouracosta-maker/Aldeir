using ReaStudio.Core.Binary;
using ReaStudio.Core.Fallback;
using ReaStudio.Core.Mcp;
using ReaStudio.Core.Security;
using Xunit;

namespace ReaStudio.Tests;

public class ToolAuthorizationTests
{
    static AuthContext Ctx(bool confirmed = false, bool switched = false, params string[] done)
        => new(confirmed, switched, new HashSet<string>(done));

    [Fact]
    public void UnknownTool_IsTreatedAsMutating_AndNeedsConfirmation()
    {
        var a = new ToolAuthorizer();
        Assert.Equal(ToolRisk.Mutating, a.RiskOf("qualquer"));
        Assert.False(a.Authorize(new("1", "qualquer"), Ctx()).Allowed);
        Assert.True(a.Authorize(new("1", "qualquer"), Ctx(confirmed: true)).Allowed);
    }

    [Fact]
    public void ReadOnlyAllowlisted_Passes() =>
        Assert.True(new ToolAuthorizer(new Dictionary<string, ToolRisk> { ["list_functions"] = ToolRisk.ReadOnly })
            .Authorize(new("1", "list_functions"), Ctx(switched: true)).Allowed);

    [Fact]
    public void AfterSwitch_NewMutation_RequiresFreshConfirmation()
    {
        var d = new ToolAuthorizer().Authorize(new("2", "rename"), Ctx(confirmed: false, switched: true));
        Assert.False(d.Allowed);
        Assert.Contains("trocado", d.Reason);
    }

    [Fact]
    public void AlreadyExecutedOperation_IsNeverRepeated_EvenIfConfirmed()
    {
        var a = new ToolAuthorizer(new Dictionary<string, ToolRisk> { ["delete_file"] = ToolRisk.Destructive });
        var d = a.Authorize(new("op-9", "delete_file"), Ctx(confirmed: true, switched: true, "op-9"));
        Assert.False(d.Allowed);
        Assert.Contains("não será repetida", d.Reason);
    }
}

public class McpTests
{
    [Fact]
    public async Task Connects_ListsTools_IgnoringNoise()
    {
        var c = new McpClient(new FakeMcpTransport());
        await c.InitializeAsync(default);
        Assert.Equal("fake-rea", c.ServerName);
        var tools = await c.ListToolsAsync(default);
        Assert.Equal(new[] { "list_functions", "rename" }, tools.Select(t => t.Name));
    }

    [Fact]
    public async Task ServerError_BecomesMcpException()
    {
        var c = new McpClient(new FakeMcpTransport());
        await Assert.ThrowsAsync<McpException>(() => c.CallToolAsync("x", new Dictionary<string, object?>(), default));
    }

    [Fact]
    public void RegistryInspector_ParsesToml_AndDropsEnv()
    {
        const string toml = "[mcp_servers.rea]\ncommand = \"C:\\\\rea\\\\rea.exe\"\nargs = [\"--mcp\", \"--x\"]\n[mcp_servers.rea.env]\nAPI_KEY = \"segredo\"\n[other]\nx=1\n";
        var s = McpRegistryInspector.ParseToml(toml, "t");
        var e = Assert.Single(s);
        Assert.Equal("rea", e.Name);
        Assert.Equal(new[] { "--mcp", "--x" }, e.Args);
        Assert.DoesNotContain("segredo", e.ToString());
    }

    [Fact]
    public void RegistryInspector_ParsesJson()
    {
        var s = McpRegistryInspector.ParseJson("{\"mcpServers\":{\"rea\":{\"command\":\"node\",\"args\":[\"a.js\"],\"env\":{\"K\":\"v\"}}}}", "j");
        Assert.Equal("node", Assert.Single(s).Command);
    }

    [Fact]
    public void RegistryInspector_IsReadOnly()
    {
        var f = Path.GetTempFileName();
        File.WriteAllText(f, "[mcp_servers.rea]\ncommand = \"x\"\n");
        var before = File.GetLastWriteTimeUtc(f);
        Assert.Single(McpRegistryInspector.ReadAll(new[] { f }));
        Assert.Equal(before, File.GetLastWriteTimeUtc(f));
        File.Delete(f);
    }
}

public class BinaryAndSecurityTests
{
    [Fact]
    public void Detects_Pe64()
    {
        var b = new byte[0x200];
        b[0] = (byte)'M'; b[1] = (byte)'Z'; b[0x3C] = 0x80;
        b[0x80] = (byte)'P'; b[0x81] = (byte)'E';
        b[0x84] = 0x64; b[0x85] = 0x86; b[0x98] = 0x0B; b[0x99] = 0x02;
        var i = BinaryFormatDetector.Detect(b);
        Assert.Equal((BinaryFormat.Pe, 64, "x86-64"), (i.Format, i.Bits, i.Architecture));
    }

    [Fact]
    public void Detects_Elf64_X8664()
    {
        var b = new byte[64];
        b[0] = 0x7F; b[1] = (byte)'E'; b[2] = (byte)'L'; b[3] = (byte)'F'; b[4] = 2; b[5] = 1; b[18] = 62;
        var i = BinaryFormatDetector.Detect(b);
        Assert.Equal((BinaryFormat.Elf, 64, "x86-64"), (i.Format, i.Bits, i.Architecture));
    }

    [Fact]
    public void UnknownBytes_AreUnknown() => Assert.Equal(BinaryFormat.Unknown, BinaryFormatDetector.Detect(new byte[] { 1, 2, 3 }).Format);

    [Fact]
    public void Log_NeverContainsSecrets()
    {
        var path = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".jsonl");
        var log = new StructuredLog(path);
        log.Write("info", "teste", new Dictionary<string, object?> { ["apiKey"] = "sk-SEGREDO123456789", ["nota"] = "usei Bearer abc.def.ghi e sk-OUTRO123456789" });
        var text = File.ReadAllText(path);
        Assert.DoesNotContain("SEGREDO", text);
        Assert.DoesNotContain("abc.def", text);
        Assert.DoesNotContain("OUTRO", text);
        Assert.Contains("[REDACTED]", text);
        File.Delete(path);
    }

    [Fact]
    public void InMemoryCredentialStore_RoundTrips()
    {
        var s = new InMemoryCredentialStore();
        s.Save("a", "x");
        Assert.Equal("x", s.TryGet("a"));
        s.Delete("a");
        Assert.Null(s.TryGet("a"));
    }
}
