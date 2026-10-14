using System;
using System.IO;
using System.Runtime.InteropServices;
using WixToolset.Dtf.WindowsInstaller;

namespace Chzzk.Installer
{
    internal static class InstallerDiagnostics
    {
        private static readonly object sync = new object();
        public static string LogPath { get; private set; }
        public static void Write(string stage, Exception error = null)
        {
            try
            {
                lock (sync)
                {
                    if (LogPath == null)
                    {
                        string root = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                        if (string.IsNullOrEmpty(root)) root = Path.GetTempPath();
                        string directory = Path.Combine(root, "ChzzkAutoCategory", "logs");
                        Directory.CreateDirectory(directory);
                        LogPath = Path.Combine(directory, "msi-ui-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + ".log");
                    }
                    File.AppendAllText(LogPath, DateTime.Now.ToString("O") + " " + stage +
                        (error == null ? "" : Environment.NewLine + error) + Environment.NewLine);
                }
            }
            catch { /* Logging failures must never abort installation. */ }
        }
        public static void Fallback(Session session, Exception error)
        {
            Write("Initialization failed; using native MSI UI.", error);
            try { session.Log("CHZZK UI initialization failed: " + error); } catch { }
            try
            {
                MessageBox(IntPtr.Zero,
                    "전용 설치 화면을 열지 못해 기본 설치 화면으로 전환합니다.\n\n오류 로그: " +
                    (LogPath ?? "MSI 설치 로그를 확인해 주세요."), "CHZZK 설치 안내", 0x30);
            }
            catch { }
        }
        [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "MessageBoxW")]
        private static extern int MessageBox(IntPtr owner, string text, string title, uint flags);
    }
}
