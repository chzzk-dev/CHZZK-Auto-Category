using System;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows;
using Chzzk.Installer;

internal static class UiSmoke
{
    [STAThread]
    static int Main()
    {
        try
        {
            var type = typeof(InstallState).Assembly.GetType("Chzzk.Installer.SetupWindow", true);
            foreach (var mode in new[] { "install", "upgrade", "repair", "remove" })
            using (var start = new ManualResetEvent(false))
            {
                var state = new InstallState();
                object view = Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                    null, new object[] { start, state, Path.Combine(Path.GetTempPath(), "ChzzkUiSmoke"), "0.0.0",
                        mode == "repair" || mode == "remove", mode == "upgrade", mode == "remove", "", "" }, null);
                var window = (Window)type.GetProperty("Window").GetValue(view);
                window.Show();
                window.UpdateLayout();
                if (window.Width != 1200 || window.Height != 820) throw new Exception("Unexpected installer dimensions.");
                if (start.WaitOne(0)) throw new Exception("UI loading must not start an installation.");
                state.Finish(0);
                type.GetMethod("Complete", BindingFlags.Public | BindingFlags.Instance).Invoke(view, null);
                window.UpdateLayout();
                window.Close();
                Console.WriteLine("WPF view loaded and completed: " + mode);
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
