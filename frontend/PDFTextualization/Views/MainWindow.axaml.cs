using System.Collections.Generic;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Platform.Storage;
using PDFTextualization.ViewModels;

namespace PDFTextualization.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object? sender, System.EventArgs e)
    {
        if (DataContext is MainWindowViewModel vm)
        {
            vm.PickPdfFile = PickPdfFileAsync;
            vm.PickOutputFile = PickOutputFileAsync;
        }
    }

    private async Task<string?> PickPdfFileAsync()
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Select Scanned PDF",
            AllowMultiple = false,
            FileTypeFilter = new List<FilePickerFileType>
            {
                new("PDF Files") { Patterns = new[] { "*.pdf" } },
                FilePickerFileTypes.All,
            },
        });
        return files.Count > 0 ? files[0].Path.LocalPath : null;
    }

    private async Task<string?> PickOutputFileAsync()
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Save Markdown Output",
            DefaultExtension = "md",
            FileTypeChoices = new List<FilePickerFileType>
            {
                new("Markdown Files") { Patterns = new[] { "*.md" } },
            },
        });
        return file?.Path.LocalPath;
    }
}
