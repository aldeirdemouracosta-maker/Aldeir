using System.Collections.ObjectModel;
using System.Net.Http;
using System.Text;
using ReaStudio.Core.Ai;
using ReaStudio.Core.Binary;
using ReaStudio.Core.Diagnostics;
using ReaStudio.Core.Fallback;
using ReaStudio.Core.Mcp;
using ReaStudio.Core.Security;

namespace ReaStudio.App.ViewModels;

public sealed record FileEntry(string Name, string Path, string Format);
public sealed record ChatLine(string Who, string Text);
public sealed record TaskItem(string Title, string Status);
public sealed record ProviderOption(ProviderId Id, string Label, string Status);

public sealed class MainViewModel : ObservableObject
{
    readonly HttpClient _http = new() { Timeout = TimeSpan.FromMinutes(5) };
    readonly OllamaClient _ollama;
    readonly ICredentialStore _credentials = new DpapiCredentialStore();
    readonly string _dataDir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "REA-Studio");
    readonly StructuredLog _log;
    ProviderRouter _router;
    RoutingMode _mode = RoutingMode.Automatic;
    string _chatInput = "";
    string _terminal = "";
    string _functionsText = "Painel de funções/pseudocódigo: NÃO IMPLEMENTADO nesta fase (depende do cliente REA/Ghidra validado).";
    ProviderOption? _selectedProvider;
    string? _selectedModel;
    string _cloudModel = "";
    int _taskSeq;

    public ObservableCollection<FileEntry> Files { get; } = new();
    public ObservableCollection<ChatLine> Chat { get; } = new();
    public ObservableCollection<TaskItem> Tasks { get; } = new();
    public ObservableCollection<DiagItem> Diagnostics { get; } = new();
    public ObservableCollection<ProviderOption> Providers { get; } = new();
    public ObservableCollection<string> OllamaModels { get; } = new();

    public RelayCommand OpenFolderCommand { get; }
    public RelayCommand DiagnoseCommand { get; }
    public RelayCommand SendCommand { get; }

    public MainViewModel()
    {
        _ollama = new OllamaClient(_http);
        _log = new StructuredLog(System.IO.Path.Combine(_dataDir, "logs", "studio.jsonl"));
        _router = BuildRouter();
        foreach (var (id, label) in new[] { (ProviderId.Codex, "Codex (CLI oficial)"), (ProviderId.OpenAiApi, "API OpenAI"),
                     (ProviderId.ClaudeCode, "Claude Code (CLI)"), (ProviderId.AnthropicApi, "API Anthropic"), (ProviderId.Ollama, "IA local / Ollama") })
            Providers.Add(new ProviderOption(id, label, "verificando..."));
        _selectedProvider = Providers[^1];
        OpenFolderCommand = new RelayCommand(OpenFolderAsync);
        DiagnoseCommand = new RelayCommand(DiagnoseAsync);
        SendCommand = new RelayCommand(SendAsync, () => !string.IsNullOrWhiteSpace(ChatInput));
        Append("REA Studio iniciado. Execute o diagnóstico para verificar REA, Ghidra e Ollama.");
    }

    ProviderRouter BuildRouter() => new(new IAiProvider[]
    {
        new CliAgentProvider(ProviderId.Codex, "codex"),
        new OpenAiApiProvider(_http, _credentials),
        new CliAgentProvider(ProviderId.ClaudeCode, "claude"),
        new AnthropicApiProvider(_http, _credentials),
        new OllamaProvider(_ollama)
    }, new FallbackPolicy(), new CheckpointStore(System.IO.Path.Combine(_dataDir, "checkpoints")), _log);

    public bool IsAutomatic { get => _mode == RoutingMode.Automatic; set { if (value) SetMode(RoutingMode.Automatic); } }
    public bool IsManual { get => _mode == RoutingMode.Manual; set { if (value) SetMode(RoutingMode.Manual); } }
    public bool IsLocalOnly { get => _mode == RoutingMode.LocalOnly; set { if (value) SetMode(RoutingMode.LocalOnly); } }
    void SetMode(RoutingMode m) { _mode = m; Raise(nameof(IsAutomatic)); Raise(nameof(IsManual)); Raise(nameof(IsLocalOnly)); Raise(nameof(ModeHint)); }

    public string ModeHint => _mode switch
    {
        RoutingMode.Automatic => "Usa o provedor selecionado; em limite/indisponibilidade/rede, salva checkpoint e continua no Ollama.",
        RoutingMode.Manual => "Usa somente o provedor e modelo escolhidos. Sem troca automática.",
        _ => "Somente Ollama local. Nenhum dado é enviado a serviços externos."
    };

    public ProviderOption? SelectedProvider { get => _selectedProvider; set => Set(ref _selectedProvider, value); }
    public string? SelectedModel { get => _selectedModel; set => Set(ref _selectedModel, value); }
    public string CloudModel { get => _cloudModel; set => Set(ref _cloudModel, value); }
    public string ChatInput { get => _chatInput; set { if (Set(ref _chatInput, value)) SendCommand?.NotifyCanExecute(); } }
    public string Terminal { get => _terminal; private set => Set(ref _terminal, value); }
    public string FunctionsText { get => _functionsText; private set => Set(ref _functionsText, value); }

    void Append(string line) => Terminal += $"[{DateTime.Now:HH:mm:ss}] {line}{Environment.NewLine}";

    Task OpenFolderAsync()
    {
        var dlg = new Microsoft.Win32.OpenFolderDialog { Title = "Selecionar pasta com binários" };
        if (dlg.ShowDialog() != true) return Task.CompletedTask;
        Files.Clear();
        foreach (var f in System.IO.Directory.EnumerateFiles(dlg.FolderName).Take(500))
        {
            var info = BinaryFormatDetector.DetectFile(f);
            if (info.Format == BinaryFormat.Unknown) continue;
            Files.Add(new FileEntry(System.IO.Path.GetFileName(f), f, $"{info.Format} {info.Bits}-bit {info.Architecture}"));
        }
        Append($"{Files.Count} binário(s) PE/ELF em {dlg.FolderName} (somente leitura; análise REA/Ghidra não implementada).");
        return Task.CompletedTask;
    }

    async Task DiagnoseAsync()
    {
        Diagnostics.Clear();
        foreach (var d in await EnvironmentDiagnostics.RunAsync(_ollama, null, default)) Diagnostics.Add(d);
        var disc = await _ollama.DiscoverAsync(default);
        OllamaModels.Clear();
        foreach (var m in disc.Models) OllamaModels.Add($"{m.Name}");
        var pref = OllamaClient.SelectPreferred(disc.Models);
        SelectedModel = pref?.Name;
        foreach (var m in disc.Models)
            Append($"Ollama: {m.Name} | mem. estimada {m.EstimatedMemoryBytes / 1_000_000_000.0:F1} GB | ctx configurado {m.ConfiguredContext?.ToString() ?? "?"} / máx {m.MaxContext?.ToString() ?? "?"} | ferramentas: {m.Tools}");
        for (int i = 0; i < Providers.Count; i++)
        {
            var p = Providers[i];
            var st = await ProviderStatusAsync(p.Id);
            Providers[i] = p with { Status = st };
        }
        var keep = SelectedProvider?.Id;
        SelectedProvider = Providers.FirstOrDefault(x => x.Id == keep) ?? Providers[^1];
        Append("Diagnóstico concluído.");
    }

    async Task<string> ProviderStatusAsync(ProviderId id)
    {
        IAiProvider prov = id switch
        {
            ProviderId.Codex => new CliAgentProvider(id, "codex"),
            ProviderId.ClaudeCode => new CliAgentProvider(id, "claude"),
            ProviderId.OpenAiApi => new OpenAiApiProvider(_http, _credentials),
            ProviderId.AnthropicApi => new AnthropicApiProvider(_http, _credentials),
            _ => new OllamaProvider(_ollama)
        };
        var s = await prov.GetStatusAsync(default);
        return (s.Available ? "OK: " : "indisponível: ") + s.Detail;
    }

    async Task SendAsync()
    {
        var text = ChatInput.Trim();
        ChatInput = "";
        Chat.Add(new ChatLine("Você", text));
        var task = new TaskItem($"Tarefa {++_taskSeq}: {(text.Length > 40 ? text[..40] + "…" : text)}", "em execução");
        Tasks.Add(task);
        var model = SelectedProvider?.Id == ProviderId.Ollama ? SelectedModel ?? OllamaClient.PreferredModel : CloudModel.Trim();
        var req = new RouteRequest($"tarefa-{_taskSeq}", _mode, SelectedProvider?.Id ?? ProviderId.Ollama,
            model, SelectedModel ?? OllamaClient.PreferredModel,
            Chat.Where(c => c.Who != "Sistema").Select(c => new AiMessage(c.Who == "Você" ? "user" : "assistant", c.Text)).ToList(),
            Array.Empty<string>(), Files.Select(f => f.Path).ToList());
        var outcome = await _router.RunAsync(req, default);
        var r = outcome.Result;
        var idx = Tasks.IndexOf(task);
        if (r.Success)
        {
            Chat.Add(new ChatLine($"{r.Provider} / {r.Model}", r.Text));
            Tasks[idx] = task with { Status = outcome.FallbackUsed ? "concluída (fallback local)" : "concluída" };
        }
        else
        {
            Chat.Add(new ChatLine("Sistema", $"Falha ({r.Error}): {r.Detail}"));
            Tasks[idx] = task with { Status = "falhou: " + r.Error };
        }
        if (outcome.FallbackUsed)
            Append($"Troca para Ollama após {outcome.Attempts[0].Error}. Checkpoint: {outcome.CheckpointPath}. Novas operações que alteram arquivos exigem confirmação.");
    }
}
