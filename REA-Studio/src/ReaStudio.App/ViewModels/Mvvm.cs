using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Input;

namespace ReaStudio.App.ViewModels;

public abstract class ObservableObject : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;
    protected void Raise([CallerMemberName] string? n = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(n));
    protected bool Set<T>(ref T field, T value, [CallerMemberName] string? n = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value; Raise(n); return true;
    }
}

public sealed class RelayCommand : ICommand
{
    readonly Func<object?, Task> _run;
    readonly Func<bool>? _can;
    bool _busy;
    public RelayCommand(Func<Task> run, Func<bool>? can = null) { _run = _ => run(); _can = can; }
    public event EventHandler? CanExecuteChanged;
    public void NotifyCanExecute() => CanExecuteChanged?.Invoke(this, EventArgs.Empty);
    public bool CanExecute(object? p) => !_busy && (_can?.Invoke() ?? true);
    public async void Execute(object? p)
    {
        _busy = true; CanExecuteChanged?.Invoke(this, EventArgs.Empty);
        try { await _run(p); }
        finally { _busy = false; CanExecuteChanged?.Invoke(this, EventArgs.Empty); }
    }
}
