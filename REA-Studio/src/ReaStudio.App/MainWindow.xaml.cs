using System.Windows;
using ReaStudio.App.ViewModels;

namespace ReaStudio.App;

public partial class MainWindow : Window
{
    public MainWindow() { InitializeComponent(); DataContext = new MainViewModel(); }
}
