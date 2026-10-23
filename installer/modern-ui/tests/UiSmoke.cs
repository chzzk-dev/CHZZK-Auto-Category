using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Chzzk.Installer;

internal static class UiSmoke
{
    static readonly Type ViewType = typeof(InstallState).Assembly.GetType("Chzzk.Installer.SetupWindow", true);
    static string output;
    static int checks;

    static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
        checks++;
    }
    static T Find<T>(Window window, string name) where T : FrameworkElement
    {
        var control = window.FindName(name) as T;
        Check(control != null, "Missing " + name);
        return control;
    }
    static object Create(ManualResetEvent start, InstallState state, string mode, string blocked = "")
    {
        return Activator.CreateInstance(ViewType, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            null, new object[] { start, state, Path.Combine(Path.GetTempPath(), "Chzzk UI 한글", "app"), "4.12.11",
                mode == "repair" || mode == "remove", mode == "upgrade", mode == "remove",
                Path.Combine(Path.GetTempPath(), "Chzzk installer.log"), blocked }, null);
    }
    static void Invoke(object view, string name, params object[] args)
    {
        ViewType.GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic).Invoke(view, args);
    }
    static void Click(Window window, string name)
    {
        var button = Find<Button>(window, name);
        Check(button.IsEnabled, name + " must be enabled");
        button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        window.UpdateLayout();
    }
    static void Capture(Window window, string name)
    {
        window.BeginAnimation(UIElement.OpacityProperty, null);
        window.Opacity = 1;
        window.UpdateLayout();
        var root = (FrameworkElement)window.Content;
        foreach (double scale in new[] { 1.0, 1.25, 1.5, 2.0 })
        {
            var bitmap = new RenderTargetBitmap((int)Math.Ceiling(root.ActualWidth * scale),
                (int)Math.Ceiling(root.ActualHeight * scale), 96 * scale, 96 * scale, PixelFormats.Pbgra32);
            bitmap.Render(root);
            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using (var file = File.Create(Path.Combine(output, name + "-" + scale.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture) + "x.png")))
                encoder.Save(file);
        }
    }
    static IEnumerable<Button> Buttons(DependencyObject parent)
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            if (child is Button) yield return (Button)child;
            foreach (var button in Buttons(child)) yield return button;
        }
    }
    static void Cancel(Window window, object view, InstallState state)
    {
        window.Dispatcher.BeginInvoke(DispatcherPriority.Background, new Action(() =>
        {
            foreach (Window dialog in window.OwnedWindows)
                foreach (var button in Buttons(dialog))
                    if (Convert.ToString(button.Content) == "작업 취소")
                    {
                        button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                        return;
                    }
            throw new Exception("Cancellation confirmation was not shown.");
        }));
        Invoke(view, "RequestClose");
        Check(state.CancellationRequested, "Cancel confirmation must reach MSI state.");
        Check(!Find<Button>(window, "CancelButton").IsEnabled, "Rollback cannot be canceled twice.");
        Check(!Find<Button>(window, "CloseButton").IsEnabled, "Close disabled during rollback.");
        window.Close();
        Check(window.IsVisible, "Rollback must finish before the installer closes.");
    }

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            output = Path.GetFullPath(args.Length > 0 ? args[0] : "build/installer-ui-preview");
            Directory.CreateDirectory(output);
            foreach (var mode in new[] { "install", "upgrade", "repair", "remove" })
            using (var start = new ManualResetEvent(false))
            {
                var state = new InstallState();
                object view = Create(start, state, mode);
                var window = (Window)ViewType.GetProperty("Window").GetValue(view);
                window.Show();
                window.UpdateLayout();
                Check(window.Width == 410 && window.Height == 274, "Compact splash dimensions.");
                if (mode == "install") Capture(window, "01-splash");
                Check(!start.WaitOne(0), "Loading must not start MSI.");
                Invoke(view, "ShowWizard");
                window.UpdateLayout();
                Check(window.Width == 690 && window.Height == 450, "Compact wizard dimensions.");
                if (mode == "install")
                {
                    Check(Find<Grid>(window, "WelcomePanel").IsVisible, "Fresh install begins with introduction.");
                    Capture(window, "02-introduction");
                    Click(window, "PrimaryButton");
                    Check(!start.WaitOne(0), "Next must not start installation.");
                    Click(window, "BackButton");
                    Check(Find<Grid>(window, "WelcomePanel").IsVisible, "Back returns to introduction.");
                    Click(window, "PrimaryButton");
                    Find<TextBox>(window, "InstallFolder").Text = "relative-folder";
                    Click(window, "PrimaryButton");
                    Check(Find<TextBlock>(window, "FolderError").IsVisible && !start.WaitOne(0), "Invalid folder blocks MSI.");
                    Find<TextBox>(window, "InstallFolder").Text = Path.Combine(Path.GetTempPath(), "Chzzk UI 한글", "app");
                    Find<TextBlock>(window, "FolderError").Visibility = Visibility.Collapsed;
                    Capture(window, "03-install-options");
                }
                else
                {
                    Check(!Find<Grid>(window, "WelcomePanel").IsVisible, "Maintenance skips introduction.");
                    Check(Find<TextBox>(window, "InstallFolder").IsReadOnly, "Existing folder remains fixed.");
                    Check(!Find<Button>(window, "BrowseButton").IsEnabled, "Existing folder cannot be browsed.");
                    if (mode == "repair")
                    {
                        Click(window, "RemoveButton");
                        Check(!Find<CheckBox>(window, "LaunchCheckBox").IsVisible, "Removal hides launch option.");
                        Click(window, "RepairButton");
                        Check(Find<CheckBox>(window, "LaunchCheckBox").IsVisible, "Repair restores launch option.");
                    }
                    Capture(window, mode + "-options");
                }
                Check(!start.WaitOne(0), "Options must wait for explicit confirmation.");
                Find<CheckBox>(window, "LaunchCheckBox").IsChecked = mode != "install";
                Click(window, "PrimaryButton");
                Check(start.WaitOne(0), "Primary confirmation signals MSI.");
                Check((bool)ViewType.GetProperty("Started").GetValue(view), "Started follows confirmation.");
                Check((bool)ViewType.GetProperty("LaunchSelected").GetValue(view) == (mode != "install"), "Launch checkbox is respected.");
                Check(Find<Grid>(window, "ProgressPanel").IsVisible, "Progress screen shown.");
                Check(!Find<Button>(window, "BackButton").IsVisible, "No back navigation while MSI runs.");
                state.ProgressRecord(new[] { 0, 100, 0, 0 });
                state.ProgressRecord(new[] { 0, 100, 0, 1 });
                state.ProgressRecord(new[] { 2, 50 });
                Invoke(view, "UpdateProgress", "프로그램 파일을 설치하고 있습니다.");
                Check(!Find<ProgressBar>(window, "InstallProgress").IsIndeterminate, "MSI ticks control progress.");
                Check(Math.Abs(Find<ProgressBar>(window, "InstallProgress").Value - 62) < 0.01, "Real MSI progress is displayed.");
                Capture(window, mode == "install" ? "04-install-progress" : mode + "-progress");
                state.Finish(0);
                Check(state.CanLaunch((SetupOperation)ViewType.GetProperty("Operation").GetValue(view),
                    (bool)ViewType.GetProperty("LaunchSelected").GetValue(view)) == (mode == "upgrade" || mode == "repair"), "Only selected successful non-removal operations may launch.");
                Invoke(view, "Complete");
                Check(Find<Grid>(window, "ResultPanel").IsVisible, "Result screen shown.");
                Check(!Find<Button>(window, "CancelButton").IsVisible, "Finished operation cannot be canceled.");
                Capture(window, mode == "install" ? "05-install-complete" : mode + "-complete");
                window.Close();
                Console.WriteLine("WPF flow passed: " + mode);
            }
            foreach (int code in new[] { 3010, 1603, 1602 })
            using (var start = new ManualResetEvent(false))
            {
                var state = new InstallState();
                var view = Create(start, state, "upgrade");
                var window = (Window)ViewType.GetProperty("Window").GetValue(view);
                window.Show();
                Invoke(view, "ShowWizard");
                Click(window, "PrimaryButton");
                if (code == 1602) Cancel(window, view, state);
                state.Finish(code);
                Invoke(view, "Complete");
                Check(!state.CanLaunch(SetupOperation.Install, true), "Non-success must not launch.");
                string expected = code == 3010 ? "다시 시작" : code == 1602 ? "취소" : "완료하지 못";
                Check(Find<TextBlock>(window, "ResultTitle").Text.Contains(expected), "Outcome remains distinct: " + code);
                Capture(window, "result-" + code);
                window.Close();
            }
            using (var start = new ManualResetEvent(false))
            {
                var view = Create(start, new InstallState(), "install", "기존 EXE 설치본을 먼저 제거해 주세요.");
                var window = (Window)ViewType.GetProperty("Window").GetValue(view);
                window.Show();
                Invoke(view, "ShowWizard");
                Check(!Find<Button>(window, "PrimaryButton").IsEnabled, "Preflight failure blocks MSI.");
                Check(Find<TextBlock>(window, "FolderError").IsVisible && !start.WaitOne(0), "Preflight reason remains visible.");
                Capture(window, "blocked-install");
                window.Close();
            }
            Console.WriteLine(checks + " WPF assertions passed; PNGs: " + output);
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
