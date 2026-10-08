using System.Diagnostics;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace IFsCompanion;

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new CompanionWindow(args));
    }
}

sealed class CompanionWindow : Form
{
    readonly WebView2 view = new() { Dock = DockStyle.Fill };
    readonly Label loading = new() { Text = "Starting IFsCompanion…", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter };
    readonly string dataRoot = Environment.GetEnvironmentVariable("IFS_VETTING_DATA_DIR") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "IFsModelVetting");
    readonly string? smokeOutput;
    Process? backend;
    string? origin;
    bool closing;
    bool pickingFolder;

    public CompanionWindow(string[] args)
    {
        smokeOutput = args.Length == 2 && args[0] == "--smoke-test" ? Path.GetFullPath(args[1]) : null;
        Text = "IFsCompanion";
        Width = 1320; Height = 920; MinimumSize = new Size(900, 650);
        StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(view); Controls.Add(loading);
        Shown += async (_, _) => await StartAsync();
        FormClosing += ClosingAsync;
    }

    async Task StartAsync()
    {
        try
        {
            Directory.CreateDirectory(dataRoot);
            // A redirected input pipe also makes the engine exit if this host crashes.
            backend = new Process { StartInfo = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "engine", "IFsCompanionEngine.exe")) {
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
                RedirectStandardOutput = true, WorkingDirectory = AppContext.BaseDirectory
            }};
            backend.Start();
            var ready = await backend.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(60));
            if (ready == null) throw new Exception("The local engine did not start. See application.log in " + dataRoot);
            origin = JsonDocument.Parse(ready).RootElement.GetProperty("url").GetString()!;
            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(dataRoot, "WebView2"));
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.Settings.AreDevToolsEnabled = false;
            view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            view.CoreWebView2.Settings.IsStatusBarEnabled = false;
            view.CoreWebView2.NavigationStarting += (_, e) => {
                if (!e.Uri.StartsWith(origin + "/", StringComparison.Ordinal) && e.Uri != origin) e.Cancel = true;
            };
            view.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
            view.CoreWebView2.WebMessageReceived += FolderRequested;
            view.CoreWebView2.PermissionRequested += (_, e) => e.State = CoreWebView2PermissionState.Deny;
            view.CoreWebView2.DownloadStarting += (_, e) => {
                using var dialog = new SaveFileDialog { FileName = Path.GetFileName(e.ResultFilePath), OverwritePrompt = true };
                e.Handled = true;
                if (dialog.ShowDialog(this) == DialogResult.OK) e.ResultFilePath = dialog.FileName;
                else e.Cancel = true;
            };
            view.CoreWebView2.NavigationCompleted += async (_, e) => {
                loading.Visible = false;
                if (smokeOutput != null)
                {
                    try {
                        if (!e.IsSuccess) throw new Exception("Desktop navigation failed: " + e.WebErrorStatus);
                        using var client = new HttpClient();
                        var installation = await client.GetStringAsync(origin + "/api/installation");
                        var heading = await view.CoreWebView2.ExecuteScriptAsync("document.querySelector('h1').textContent");
                        if (JsonSerializer.Deserialize<string>(heading) != "IFsCompanion") throw new Exception("Unexpected desktop page");
                        // Exercise the real embedded shell and its live comparison workspace.
                        for (int attempt=0; attempt<100; attempt++) {
                            var readyFrame = await view.CoreWebView2.ExecuteScriptAsync("Boolean(document.getElementById('comparison')?.contentWindow.openCompanionReport)");
                            if (readyFrame == "true") break;
                            await Task.Delay(100);
                        }
                        var shell = await view.CoreWebView2.ExecuteScriptAsync("JSON.stringify({tools:document.getElementById('toolsGroup').open,recent:document.getElementById('recentGroup').open,frame:!!document.getElementById('comparison').contentWindow.openCompanionReport,composer:document.getElementById('composer').getBoundingClientRect().height})");
                        var shellState = JsonDocument.Parse(JsonSerializer.Deserialize<string>(shell)!);
                        if (!shellState.RootElement.GetProperty("frame").GetBoolean()) throw new Exception("Comparison workspace did not load");
                        if (shellState.RootElement.GetProperty("composer").GetDouble()<160) throw new Exception("Composer height is too small");
                        await view.CoreWebView2.ExecuteScriptAsync("document.getElementById('toolsGroup').open=true;document.getElementById('recentGroup').open=true;document.querySelector('[data-view=compare]').click();");
                        var visible = await view.CoreWebView2.ExecuteScriptAsync("!document.getElementById('compareView').classList.contains('hidden')");
                        if (visible!="true") throw new Exception("Tool navigation failed");
                        await view.CoreWebView2.ExecuteScriptAsync("document.querySelector('[data-view=settings]').click();document.querySelector('[data-view=companion]').click();document.getElementById('toolsGroup').open=false;document.getElementById('recentGroup').open=false;");
                        await Task.Delay(250);
                        using (var image = File.Create(smokeOutput + ".png")) await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, image);
                        File.WriteAllText(smokeOutput, JsonSerializer.Serialize(new { ok = true, heading, installation, backendPid = backend!.Id, origin }));
                    } catch (Exception ex) { File.WriteAllText(smokeOutput, JsonSerializer.Serialize(new { ok = false, error = ex.ToString() })); }
                    closing = true; Close();
                }
            };
            view.CoreWebView2.Navigate(origin + "/");
        }
        catch (Exception ex)
        {
            if (smokeOutput != null) File.WriteAllText(smokeOutput, JsonSerializer.Serialize(new { ok = false, error = ex.ToString() }));
            else MessageBox.Show(this, "IFsCompanion could not start.\n\n" + ex.Message + "\n\nIf WebView2 is missing, rerun the installer.", "IFsCompanion", MessageBoxButtons.OK, MessageBoxIcon.Error);
            closing = true; Close();
        }
    }

    void FolderRequested(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (closing || pickingFolder || e.Source != origin + "/") return;
        using var message = JsonDocument.Parse(e.WebMessageAsJson);
        if (!message.RootElement.TryGetProperty("type", out var type) || type.GetString() != "select-installation") return;
        var initial = message.RootElement.GetProperty("installation").GetString() ?? "";
        pickingFolder = true;
        // Leave the WebView2 callback before entering a modal Windows message loop.
        BeginInvoke((Action)(() => {
            try {
                if (closing || IsDisposed) return;
                using var dialog = new FolderBrowserDialog {
                    Description = "Select IFs installation folder", UseDescriptionForTitle = true,
                    SelectedPath = initial, ShowNewFolderButton = false
                };
                var selected = dialog.ShowDialog(this) == DialogResult.OK ? dialog.SelectedPath : null;
                view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { type = "installation-selected", installation = selected }));
            } catch (Exception ex) {
                if (!closing && !IsDisposed)
                    view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { type = "installation-selected", error = ex.Message }));
            } finally { pickingFolder = false; }
        }));
    }

    async void ClosingAsync(object? sender, FormClosingEventArgs e)
    {
        if (!closing && origin != null)
        {
            e.Cancel = true;
            Enabled = false;
            try {
                using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
                var state = JsonDocument.Parse(await client.GetStringAsync(origin + "/api/status"));
                if (state.RootElement.GetProperty("running").GetBoolean() && MessageBox.Show(this,
                    "A tool is running work. Close IFsCompanion and interrupt it?", "IFsCompanion", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            } catch { /* An unavailable engine must not prevent closing the app. */ }
            finally { Enabled = true; }
            closing = true; Close(); return;
        }
        view.Dispose();
        if (backend != null)
        {
            try {
                if (!backend.HasExited) {
                    backend.StandardInput.Close();
                    if (!backend.WaitForExit(3000)) backend.Kill(entireProcessTree: true);
                }
            } catch (InvalidOperationException) { }
            backend.Dispose();
        }
    }
}
