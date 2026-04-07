using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Avalonia.Platform.Storage;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace PDFTextualization.ViewModels;

public partial class MainWindowViewModel : ViewModelBase
{
    // ── File paths ────────────────────────────────────────────────
    [ObservableProperty] private string _inputPdf = "";
    [ObservableProperty] private string _outputMd = "";

    // ── OCR API (GLM-OCR, fixed endpoint) ────────────────────────
    [ObservableProperty] private string _ocrApiKey = "";

    // ── LLM API ───────────────────────────────────────────────────
    [ObservableProperty] private string _llmProvider = "GLM";   // "GLM" or "OpenAI Compatible"
    [ObservableProperty] private string _llmApiKey = "";
    [ObservableProperty] private string _llmBaseUrl = "https://open.bigmodel.cn/api/paas/v4/";
    [ObservableProperty] private string _llmModel = "glm-4.6";
    [ObservableProperty] private bool _llmEnabled = true;

    // ── Other settings ────────────────────────────────────────────
    [ObservableProperty] private string _pageRange = "";
    [ObservableProperty] private int _llmMaxConcurrent = 3;

    // ── Status ────────────────────────────────────────────────────
    [ObservableProperty] private double _progressValue = 0;
    [ObservableProperty] private int _progressMax = 100;
    [ObservableProperty] private string _statusText = "Ready";
    [ObservableProperty] private bool _isRunning = false;
    [ObservableProperty] private bool _canOpenResult = false;
    [ObservableProperty] private string _logText = "";

    // ── Derived: show Base URL field only for OpenAI-compatible ───
    public bool IsLlmBaseUrlVisible => LlmProvider == "OpenAI Compatible";

    partial void OnLlmProviderChanged(string value)
    {
        // Auto-fill base URL when switching provider
        if (value == "GLM")
            LlmBaseUrl = "https://open.bigmodel.cn/api/paas/v4/";
        else if (value == "OpenAI Compatible" && LlmBaseUrl == "https://open.bigmodel.cn/api/paas/v4/")
            LlmBaseUrl = "https://api.openai.com/v1/";

        OnPropertyChanged(nameof(IsLlmBaseUrlVisible));
    }

    private CancellationTokenSource? _cts;

    public Func<Task<string?>>? PickPdfFile { get; set; }
    public Func<Task<string?>>? PickOutputFile { get; set; }

    [RelayCommand]
    private async Task BrowseInputAsync()
    {
        if (PickPdfFile is null) return;
        var path = await PickPdfFile();
        if (path is not null)
        {
            InputPdf = path;
            if (string.IsNullOrWhiteSpace(OutputMd))
                OutputMd = Path.ChangeExtension(path, ".md");
        }
    }

    [RelayCommand]
    private async Task BrowseOutputAsync()
    {
        if (PickOutputFile is null) return;
        var path = await PickOutputFile();
        if (path is not null)
            OutputMd = path;
    }

    [RelayCommand]
    private async Task StartAsync()
    {
        if (string.IsNullOrWhiteSpace(InputPdf) || string.IsNullOrWhiteSpace(OcrApiKey))
        {
            AppendLog("ERROR: Input PDF and OCR API key are required.");
            return;
        }

        IsRunning = true;
        CanOpenResult = false;
        ProgressValue = 0;
        ProgressMax = 100;
        StatusText = "Starting…";
        LogText = "";
        _cts = new CancellationTokenSource();

        try { await RunPipelineAsync(_cts.Token); }
        catch (OperationCanceledException) { AppendLog("Cancelled."); StatusText = "Cancelled"; }
        catch (Exception ex) { AppendLog($"ERROR: {ex.Message}"); StatusText = "Error"; }
        finally { IsRunning = false; }
    }

    [RelayCommand]
    private void Stop() { _cts?.Cancel(); StatusText = "Stopping…"; }

    [RelayCommand]
    private void OpenResult()
    {
        if (!File.Exists(OutputMd)) return;
        Process.Start(new ProcessStartInfo(OutputMd) { UseShellExecute = true });
    }

    private async Task RunPipelineAsync(CancellationToken ct)
    {
        var python = FindPython();
        if (python is null)
        {
            AppendLog("ERROR: python3 / python not found.");
            StatusText = "Error: Python not found";
            return;
        }

        var scriptDir = GetBackendDir();
        var scriptPath = Path.Combine(scriptDir, "main.py");
        if (!File.Exists(scriptPath))
        {
            AppendLog($"ERROR: backend not found at {scriptPath}");
            StatusText = "Error: backend not found";
            return;
        }

        var args = BuildArgs(scriptPath);
        AppendLog($"Running: {python} {args}");

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = args,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = scriptDir,
        };

        using var proc = new Process { StartInfo = psi };
        proc.Start();
        await Task.WhenAll(ReadStreamAsync(proc.StandardOutput, ct),
                           ReadStderrAsync(proc.StandardError, ct));
        await proc.WaitForExitAsync(ct);
    }

    private async Task ReadStreamAsync(StreamReader reader, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            if (line is null) break;
            HandleProgressLine(line);
        }
    }

    private async Task ReadStderrAsync(StreamReader reader, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            if (line is null) break;
            if (!string.IsNullOrWhiteSpace(line)) AppendLog($"[stderr] {line}");
        }
    }

    private void HandleProgressLine(string line)
    {
        AppendLog(line);
        try
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            switch (root.GetProperty("type").GetString())
            {
                case "progress":
                    var page = root.GetProperty("page").GetInt32();
                    var total = root.GetProperty("total").GetInt32();
                    var status = root.GetProperty("status").GetString();
                    ProgressMax = total * 2;
                    ProgressValue = status == "llm_done" ? page * 2 : page * 2 - 1;
                    StatusText = $"Page {page}/{total} — {status}";
                    break;
                case "done":
                    var pages = root.TryGetProperty("pages", out var p) ? p.GetInt32() : 0;
                    StatusText = $"Done! {pages} pages → {OutputMd}";
                    ProgressValue = ProgressMax;
                    CanOpenResult = File.Exists(OutputMd);
                    break;
                case "error":
                    StatusText = $"Warning: {root.GetProperty("message").GetString()}";
                    break;
            }
        }
        catch { }
    }

    private string BuildArgs(string scriptPath)
    {
        var sb = new System.Text.StringBuilder();
        sb.Append($"\"{scriptPath}\" \"{InputPdf}\"");
        sb.Append($" -o \"{OutputMd}\"");

        // OCR API
        sb.Append($" --ocr-api-key \"{OcrApiKey}\"");

        // LLM API
        var llmKey = string.IsNullOrWhiteSpace(LlmApiKey) ? OcrApiKey : LlmApiKey;
        sb.Append($" --llm-api-key \"{llmKey}\"");
        sb.Append($" --llm-base-url \"{LlmBaseUrl}\"");
        sb.Append($" --llm-provider \"{(LlmProvider == "GLM" ? "glm" : "openai")}\"");
        sb.Append($" --llm-model \"{LlmModel}\"");

        if (!LlmEnabled) sb.Append(" --no-llm");
        if (LlmMaxConcurrent > 0) sb.Append($" --llm-max-concurrent {LlmMaxConcurrent}");
        if (!string.IsNullOrWhiteSpace(PageRange)) sb.Append($" --pages {PageRange}");
        return sb.ToString();
    }

    private void AppendLog(string line) => LogText += line + "\n";

    private static string? FindPython()
    {
        foreach (var candidate in new[] { "python3", "python" })
        {
            try
            {
                var psi = new ProcessStartInfo(candidate, "--version")
                { UseShellExecute = false, RedirectStandardOutput = true,
                  RedirectStandardError = true, CreateNoWindow = true };
                using var proc = Process.Start(psi);
                proc?.WaitForExit(3000);
                if (proc?.ExitCode == 0) return candidate;
            }
            catch { }
        }
        return null;
    }

    private static string GetBackendDir()
    {
        var exeDir = AppContext.BaseDirectory;
        foreach (var rel in new[] { "backend", "../../../backend", "../../../../backend" })
        {
            var candidate = Path.GetFullPath(Path.Combine(exeDir, rel));
            if (Directory.Exists(candidate)) return candidate;
        }
        return Path.Combine(exeDir, "backend");
    }
}
