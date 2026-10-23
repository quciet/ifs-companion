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
    string dataRoot = Path.Combine(AppContext.BaseDirectory, "data");
    readonly string? smokeOutput;
    Process? backend;
    string? origin;
    bool closing;
    bool pickingFolder;

    public CompanionWindow(string[] args)
    {
        smokeOutput = args.Length == 2 && args[0] == "--smoke-test" ? Path.GetFullPath(args[1]) : null;
        Text = "IFsCompanion";
        Icon = System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath);
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
            // A redirected input pipe also makes the engine exit if this host crashes.
            backend = new Process { StartInfo = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "python", "python.exe")) {
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
                RedirectStandardOutput = true, WorkingDirectory = AppContext.BaseDirectory
            }};
            backend.StartInfo.ArgumentList.Add("-I");
            backend.StartInfo.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory, "engine", "desktop_launcher.py"));
            backend.StartInfo.Environment["IFS_COMPANION_PYTHON"] = Path.Combine(AppContext.BaseDirectory, "python", "python.exe");
            backend.StartInfo.Environment["IFS_COMPANION_PACKAGED"] = "1";
            backend.StartInfo.Environment["IFS_COMPANION_APP_DIR"] = AppContext.BaseDirectory;
            backend.Start();
            // First launch or a storage change may copy large tool packages/results.
            loading.Text = "Preparing Companion storage…";
            var ready = await backend.StandardOutput.ReadLineAsync();
            if (ready == null) throw new Exception("The local engine did not start. See application.log in " + dataRoot);
            using var startup = JsonDocument.Parse(ready);
            if (startup.RootElement.TryGetProperty("error", out var startupError)) throw new Exception(startupError.GetString());
            dataRoot = startup.RootElement.GetProperty("data_root").GetString()!;
            origin = startup.RootElement.GetProperty("url").GetString()!;
            foreach (var variable in new[] { "TEMP", "TMP", "TMPDIR" })
                Environment.SetEnvironmentVariable(variable, Path.Combine(dataRoot, "temp"));
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
                        if (shellState.RootElement.GetProperty("composer").GetDouble()<=0) throw new Exception("Message composer is not visible");
                        var usableComposer = await view.CoreWebView2.ExecuteScriptAsync("Boolean(document.getElementById('prompt') && document.querySelector('#composer button[type=submit]') && !document.getElementById('prompt').disabled)");
                        if (usableComposer!="true") throw new Exception("Message controls are unavailable");
                        await view.CoreWebView2.ExecuteScriptAsync("document.getElementById('toolsGroup').open=true;document.getElementById('recentGroup').open=true;document.querySelector('[data-view=compare]').click();");
                        var visible = await view.CoreWebView2.ExecuteScriptAsync("!document.getElementById('compareView').classList.contains('hidden')");
                        if (visible!="true") throw new Exception("Tool navigation failed");
                        await view.CoreWebView2.ExecuteScriptAsync("document.querySelector('[data-view=settings]').click();document.querySelector('[data-view=companion]').click();document.getElementById('toolsGroup').open=false;document.getElementById('recentGroup').open=false;");
                        await view.CoreWebView2.ExecuteScriptAsync("document.querySelector('[data-view=settings]').click();");
                        var storageLabel = await view.CoreWebView2.ExecuteScriptAsync("document.getElementById('storageCurrent').textContent");
                        if (!(JsonSerializer.Deserialize<string>(storageLabel) ?? "").Contains(dataRoot)) throw new Exception("Storage setting did not display the active data folder");
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
        if (!message.RootElement.TryGetProperty("type", out var type)) return;
        if (type.GetString() == "install-companion-update") {
            BeginInvoke((Action)(async () => await InstallUpdateAsync()));
            return;
        }
        if (type.GetString() == "open-companion-release") {
            var url = message.RootElement.GetProperty("url").GetString() ?? "";
            if (System.Text.RegularExpressions.Regex.IsMatch(url, @"^https://github\.com/quciet/ifs-companion/releases/tag/v\d+\.\d+\.\d+$"))
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            return;
        }
        if (type.GetString() != "select-installation" && type.GetString() != "select-storage") return;
        bool storageFolder = type.GetString() == "select-storage";
        var initial = message.RootElement.GetProperty("installation").GetString() ?? "";
        pickingFolder = true;
        // Leave the WebView2 callback before entering a modal Windows message loop.
        BeginInvoke((Action)(() => {
            try {
                if (closing || IsDisposed) return;
                using var dialog = new FolderBrowserDialog {
                    Description = storageFolder ? "Select an empty Companion storage folder" : "Select IFs installation folder", UseDescriptionForTitle = true,
                    SelectedPath = initial, ShowNewFolderButton = storageFolder
                };
                var selected = dialog.ShowDialog(this) == DialogResult.OK ? dialog.SelectedPath : null;
                view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { type = storageFolder ? "storage-selected" : "installation-selected", installation = selected }));
            } catch (Exception ex) {
                if (!closing && !IsDisposed)
                    view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { type = storageFolder ? "storage-selected" : "installation-selected", error = ex.Message }));
            } finally { pickingFolder = false; }
        }));
    }

    async Task InstallUpdateAsync()
    {
        if (closing || origin == null) return;
        try {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
            var tokenJson = await view.CoreWebView2.ExecuteScriptAsync("document.querySelector('meta[name=companion-token]').content");
            client.DefaultRequestHeaders.Add("X-Companion-Token", JsonSerializer.Deserialize<string>(tokenJson));
            using var response = await client.PostAsync(origin + "/api/app-update/install", new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));
            using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            if (!response.IsSuccessStatusCode) throw new Exception(document.RootElement.GetProperty("error").GetString());
            var path = Path.GetFullPath(document.RootElement.GetProperty("path").GetString()!);
            var directory = Path.GetFullPath(Path.Combine(dataRoot, "updates")) + Path.DirectorySeparatorChar;
            if (!path.StartsWith(directory, StringComparison.OrdinalIgnoreCase) || !Path.GetFileName(path).StartsWith("IFsCompanion-Setup-", StringComparison.Ordinal) || !path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) throw new Exception("Invalid update package location.");
            var digest = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
            if (digest != document.RootElement.GetProperty("sha256").GetString()) throw new Exception("Update checksum changed. Download it again.");
            if (!File.Exists(Path.Combine(AppContext.BaseDirectory, "unins000.exe"))) throw new Exception("This copy uses portable updates. Download and extract the ZIP after closing Companion.");
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true, Arguments = "/CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /DIR=\"" + AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar) + "\"" });
            closing = true;
            Close();
        } catch (Exception error) {
            if (!closing) view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { type = "companion-update-result", error = error.Message }));
        }
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
