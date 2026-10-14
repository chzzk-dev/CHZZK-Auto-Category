using System;
using System.IO;
using System.Threading;
using System.Windows;
using Microsoft.Win32;
using WixToolset.Dtf.WindowsInstaller;

namespace Chzzk.Installer
{
    public sealed class EmbeddedInstallerUI : IEmbeddedUI
    {
        private readonly ManualResetEvent start = new ManualResetEvent(false);
        private readonly ManualResetEvent exit = new ManualResetEvent(false);
        private readonly InstallState state = new InstallState();
        private Thread uiThread;
        private SetupWindow view;
        private Exception startupFailure;

        public bool Initialize(Session session, string resourcePath, ref InstallUIOptions internalUILevel)
        {
            // /passive and /qn stay unattended. The updater owns their visible progress UI.
            if (((int)internalUILevel & 7) != (int)InstallUIOptions.Full) return false;
            var originalLevel = internalUILevel;
            try
            {
                InstallerDiagnostics.Write("Initialize: CLR " + Environment.Version + "; pointer size " + IntPtr.Size);
                if (session["CHZZK_USE_NATIVE_UI"] == "1") return false;
                return InitializeCore(session, resourcePath, ref internalUILevel);
            }
            catch (InstallCanceledException) { throw; }
            catch (Exception ex)
            {
                if (view != null && uiThread != null && uiThread.IsAlive)
                    view.Window.Dispatcher.BeginInvoke(new Action(() => view.Abort()));
                try { session["CHZZK_MODERN_UI"] = ""; } catch { }
                internalUILevel = originalLevel;
                InstallerDiagnostics.Fallback(session, ex);
                return false;
            }
        }

        private static string RegistryValue(RegistryHive hive, RegistryView registryView, string key, string name)
        {
            try
            {
                using (var root = RegistryKey.OpenBaseKey(hive, registryView))
                using (var entry = root.OpenSubKey(key))
                    return entry == null ? "" : Convert.ToString(entry.GetValue(name)) ?? "";
            }
            catch (Exception ex) { InstallerDiagnostics.Write("Registry lookup: " + key, ex); return ""; }
        }

        private bool InitializeCore(Session session, string resourcePath, ref InstallUIOptions internalUILevel)
        {
            string commandFolder = session["INSTALLFOLDER"];
            // Initialization reads MSI properties and the previous folder; the engine
            // executes AppSearch in its normal sequence after the UI has initialized.
            string registeredFolder = RegistryValue(RegistryHive.LocalMachine, RegistryView.Registry64,
                @"Software\CHZZK Dev\AutoCategory", "InstallDir");
            bool installed = !string.IsNullOrEmpty(session["Installed"]);
            bool remove = string.Equals(session["REMOVE"], "ALL", StringComparison.OrdinalIgnoreCase);
            string folder = !string.IsNullOrEmpty(registeredFolder) ? registeredFolder : commandFolder;
            bool upgrade = !installed && !string.IsNullOrEmpty(registeredFolder);
            if (string.IsNullOrEmpty(folder)) folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "CHZZK Auto Category");
            string version = session["ProductVersion"];
            string log = session["MsiLogFileLocation"];
            string blocked = "";
            foreach (var hive in new[] { RegistryHive.LocalMachine, RegistryHive.CurrentUser })
            foreach (var registryView in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                if (!installed && !string.IsNullOrEmpty(RegistryValue(hive, registryView,
                    @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CHZZK Auto Category", "UninstallString")))
                    blocked = "기존 EXE 설치본을 먼저 제거해 주세요. 제거할 때 사용자 설정 삭제 체크를 해제하면 기존 설정을 유지할 수 있습니다.";
            }
            uiThread = new Thread(() =>
            {
                try
                {
                    InstallerDiagnostics.Write("Creating WPF view; resources: " + string.Join(", ", typeof(EmbeddedInstallerUI).Assembly.GetManifestResourceNames()));
                    view = new SetupWindow(start, state, folder, version, installed, upgrade, remove, log, blocked);
                    InstallerDiagnostics.Write("Showing WPF view.");
                    view.Window.ShowDialog();
                }
                catch (Exception ex) { startupFailure = ex; InstallerDiagnostics.Write("WPF thread failed.", ex); }
                finally { InstallerDiagnostics.Write("WPF thread exited."); exit.Set(); }
            });
            uiThread.IsBackground = true;
            uiThread.SetApartmentState(ApartmentState.STA);
            uiThread.Start();
            int signaled = WaitHandle.WaitAny(new WaitHandle[] { start, exit });
            if (signaled == 1)
            {
                uiThread.Join();
                if (startupFailure != null)
                {
                    throw new InvalidOperationException("The embedded installer window failed to start.", startupFailure);
                }
                throw new InstallCanceledException();
            }
            // Session is only valid inside Initialize. Never pass it to WPF or retain it.
            session["INSTALLFOLDER"] = view.InstallFolder;
            session["CHZZK_MODERN_UI"] = "1";
            session["REBOOT"] = "ReallySuppress";
            if (view.Operation == SetupOperation.Remove) session["REMOVE"] = "ALL";
            else if (view.Operation == SetupOperation.Repair)
            {
                session["REINSTALL"] = "ALL";
                session["REINSTALLMODE"] = "omus";
            }
            internalUILevel = InstallUIOptions.NoChange | InstallUIOptions.SourceResolutionOnly;
            InstallerDiagnostics.Write("UI accepted; continuing MSI engine.");
            return true;
        }

        public MessageResult ProcessMessage(InstallMessage messageType, Record record,
            MessageButtons buttons, MessageIcon icon, MessageDefaultButton defaultButton)
        {
            try { return ProcessMessageCore(messageType, record, buttons, icon, defaultButton); }
            catch (Exception ex)
            {
                InstallerDiagnostics.Write("MSI message handler failed: " + messageType, ex);
                state.Finish(1603);
                return MessageResult.Cancel;
            }
        }

        private MessageResult ProcessMessageCore(InstallMessage messageType, Record record,
            MessageButtons buttons, MessageIcon icon, MessageDefaultButton defaultButton)
        {
            if (view == null) return MessageResult.None;
            if (exit.WaitOne(0) || view.Window.Dispatcher.HasShutdownStarted) return MessageResult.Cancel;
            // Consume the record while this callback owns it. WPF never retains MSI records.
            int[] numbers = new int[record == null ? 0 : record.FieldCount];
            if (messageType == InstallMessage.Progress || messageType == InstallMessage.CommonData)
                for (int i = 0; i < numbers.Length; i++) numbers[i] = record.GetInteger(i + 1);
            // INSTALLEND is not a Win32 exit-code record. Completion comes from our
            // explicit post-InstallFinalize message, where the transaction has committed.
            bool completed = messageType == InstallMessage.Info && record != null && record.GetString(0) == "CHZZK_SETUP_RESULT:[1]";
            int completionCode = completed ? record.GetInteger(1) : -1;
            string message = record == null ? "" : record.ToString();
            string action = messageType == InstallMessage.ActionStart && record != null && record.FieldCount >= 2 ? record.GetString(2) : "";
            return (MessageResult)view.Window.Dispatcher.Invoke(new Func<MessageResult>(() =>
            {
                switch (messageType)
                {
                    case InstallMessage.Progress: state.ProgressRecord(numbers); break;
                    case InstallMessage.ActionStart: state.ActionStart(); break;
                    case InstallMessage.ActionData: state.ActionData(); break;
                    case InstallMessage.CommonData:
                        if (numbers.Length >= 2 && numbers[0] == 2) view.SetCancelAllowed(numbers[1] != 0);
                        break;
                    case InstallMessage.Info:
                        if (completed) state.Finish(completionCode);
                        break;
                    case InstallMessage.InstallEnd:
                        if (state.Outcome == SetupOutcome.Unknown) state.Finish(state.CancellationRequested ? 1602 : 1603);
                        break;
                    case InstallMessage.Error:
                    case InstallMessage.Warning:
                    case InstallMessage.User:
                    case InstallMessage.FatalExit:
                    case InstallMessage.OutOfDiskSpace:
                        return EnginePrompt(messageType, message, buttons, defaultButton);
                    case InstallMessage.FilesInUse:
                        return EnginePrompt(messageType, "프로그램이 실행 중이라 파일을 변경할 수 없습니다. 트레이에서 앱을 완전히 종료한 뒤 다시 시도해 주세요.\n\n" + message, MessageButtons.AbortRetryIgnore, MessageDefaultButton.Button2);
                    case InstallMessage.RMFilesInUse:
                        int choice = view.Prompt("실행 중인 프로그램", "설치를 계속하려면 아래 프로그램을 닫아야 합니다. 저장하지 않은 작업을 먼저 저장해 주세요.\n\n" + message,
                            new[] { "프로그램 닫고 계속", "설치 취소" }, 1);
                        return choice == 0 ? MessageResult.OK : MessageResult.Cancel;
                }
                view.UpdateProgress(action);
                if ((messageType == InstallMessage.Progress || messageType == InstallMessage.ActionStart || messageType == InstallMessage.ActionData) && state.TakeCancellation()) return MessageResult.Cancel;
                return MessageResult.None;
            }));
        }
        private MessageResult EnginePrompt(InstallMessage type, string message, MessageButtons buttons, MessageDefaultButton defaultButton)
        {
            string[] labels;
            MessageResult[] results;
            switch (buttons)
            {
                case MessageButtons.OKCancel: labels = new[] { "확인", "취소" }; results = new[] { MessageResult.OK, MessageResult.Cancel }; break;
                case MessageButtons.AbortRetryIgnore: labels = new[] { "중단", "다시 시도", "무시" }; results = new[] { MessageResult.Abort, MessageResult.Retry, MessageResult.Ignore }; break;
                case MessageButtons.YesNoCancel: labels = new[] { "예", "아니요", "취소" }; results = new[] { MessageResult.Yes, MessageResult.No, MessageResult.Cancel }; break;
                case MessageButtons.YesNo: labels = new[] { "예", "아니요" }; results = new[] { MessageResult.Yes, MessageResult.No }; break;
                case MessageButtons.RetryCancel: labels = new[] { "다시 시도", "취소" }; results = new[] { MessageResult.Retry, MessageResult.Cancel }; break;
                default: labels = new[] { "확인" }; results = new[] { MessageResult.OK }; break;
            }
            int index = Math.Min(labels.Length - 1, ((int)defaultButton >> 8));
            string title = type == InstallMessage.Warning ? "설치 안내" : type == InstallMessage.User ? "작업 확인" : "설치 작업 확인";
            return results[view.Prompt(title, message, labels, index)];
        }
        public void Shutdown()
        {
            InstallerDiagnostics.Write("MSI UI shutdown; outcome " + state.Outcome);
            if (view != null && uiThread != null && uiThread.IsAlive && !view.Window.Dispatcher.HasShutdownStarted)
                view.Window.Dispatcher.BeginInvoke(new Action(() =>
                {
                    try { view.Complete(); }
                    catch (Exception ex) { InstallerDiagnostics.Write("Completion view failed.", ex); view.Abort(); }
                }));
            if (uiThread != null) uiThread.Join();
            start.Dispose();
            exit.Dispose();
        }
    }
}
