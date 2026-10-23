using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

namespace Chzzk.Installer
{
    internal sealed class SetupWindow
    {
        public Window Window { get; private set; }
        public SetupOperation Operation { get; private set; }
        public string InstallFolder { get; private set; }
        public bool LaunchSelected { get; private set; }
        public bool Started { get; private set; }
        private bool finished, cancelAllowed = true;
        private readonly ManualResetEvent start;
        private readonly InstallState state;
        private readonly string logPath, preflightError;
        private readonly bool maintenance, upgrading;
        private readonly string productVersion;
        private readonly bool hasWelcome;
        private readonly DispatcherTimer splashTimer;
        private bool onWelcome;

        public SetupWindow(ManualResetEvent startEvent, InstallState installState, string folder,
                           string version, bool installed, bool upgrade, bool remove,
                           string log, string blockedReason)
        {
            start = startEvent;
            state = installState;
            logPath = log;
            preflightError = blockedReason;
            maintenance = installed;
            upgrading = upgrade;
            productVersion = version;
            hasWelcome = !installed && !upgrade && !remove && string.IsNullOrEmpty(blockedReason);
            InstallFolder = folder;
            Operation = remove ? SetupOperation.Remove : installed ? SetupOperation.Repair : SetupOperation.Install;
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Chzzk.Installer.SetupWindow.xaml"))
            {
                if (stream == null) throw new InvalidOperationException("Installer view resource is missing.");
                Window = (Window)XamlReader.Load(stream);
            }
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Chzzk.Installer.AppIcon.ico"))
            {
                if (stream != null)
                {
                    var icon = BitmapFrame.Create(stream, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
                    icon.Freeze();
                    Window.Icon = icon;
                }
            }
            Find<TextBox>("InstallFolder").Text = folder;
            Find<TextBox>("InstallFolder").IsReadOnly = installed || upgrade;
            Find<Button>("BrowseButton").IsEnabled = !installed && !upgrade;
            Find<StackPanel>("MaintenancePanel").Visibility = installed ? Visibility.Visible : Visibility.Collapsed;
            Find<Button>("RepairButton").Click += (_, __) => SelectOperation(SetupOperation.Repair);
            Find<Button>("RemoveButton").Click += (_, __) => SelectOperation(SetupOperation.Remove);
            Find<Button>("BrowseButton").Click += Browse;
            Find<Button>("PrimaryButton").Click += Primary;
            Find<Button>("BackButton").Click += (_, __) => ShowWelcome();
            Find<Button>("CancelButton").Click += (_, __) => RequestClose();
            Find<Button>("CloseButton").Click += (_, __) => RequestClose();
            Find<Button>("MinimizeButton").Click += (_, __) => Window.WindowState = WindowState.Minimized;
            Find<Grid>("TitleBar").MouseLeftButtonDown += (_, e) =>
            {
                if (e.ChangedButton == MouseButton.Left && e.OriginalSource is TextBlock) Window.DragMove();
                else if (e.ChangedButton == MouseButton.Left && ReferenceEquals(e.OriginalSource, Find<Grid>("TitleBar"))) Window.DragMove();
            };
            Window.Closing += (_, e) =>
            {
                if (Started && !finished)
                {
                    e.Cancel = true;
                    RequestCancellation();
                }
            };
            Window.Loaded += (_, __) =>
            {
                Window.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(220)));
                splashTimer.Start();
            };
            splashTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(450) };
            splashTimer.Tick += (_, __) => ShowWizard();
            Window.Closed += (_, __) => splashTimer.Stop();
            SelectOperation(Operation);
            if (hasWelcome) ShowWelcome();
            if (!string.IsNullOrEmpty(preflightError))
            {
                Text("FolderError", preflightError);
                Find<TextBlock>("FolderError").Visibility = Visibility.Visible;
                Find<Button>("PrimaryButton").IsEnabled = false;
            }
            Find<Grid>("WizardPanel").Visibility = Visibility.Collapsed;
            Find<Grid>("SplashPanel").Visibility = Visibility.Visible;
            Window.Width = 410;
            Window.Height = 274;
        }

        private T Find<T>(string name) where T : FrameworkElement { return (T)Window.FindName(name); }
        internal void Abort() { splashTimer.Stop(); finished = true; Window.Close(); }
        private void Text(string name, string value) { Find<TextBlock>(name).Text = value; }
        internal void ShowWizard()
        {
            splashTimer.Stop();
            if (Find<Grid>("SplashPanel").Visibility != Visibility.Visible) return;
            Rect area = SystemParameters.WorkArea;
            double width = Math.Min(690, area.Width), height = Math.Min(450, area.Height);
            double left = Window.Left + (Window.Width - width) / 2;
            double top = Window.Top + (Window.Height - height) / 2;
            Window.MinWidth = width;
            Window.MinHeight = height;
            Window.Width = width;
            Window.Height = height;
            Window.Left = Math.Max(area.Left, Math.Min(area.Right - width, left));
            Window.Top = Math.Max(area.Top, Math.Min(area.Bottom - height, top));
            Find<Grid>("SplashPanel").Visibility = Visibility.Collapsed;
            Find<ProgressBar>("SplashProgress").IsIndeterminate = false;
            Find<Grid>("WizardPanel").Visibility = Visibility.Visible;
            Find<Button>("PrimaryButton").Focus();
        }
        private void ShowWelcome()
        {
            onWelcome = true;
            ShowPanel("WelcomePanel");
            Find<Button>("BackButton").Visibility = Visibility.Collapsed;
            Find<Button>("PrimaryButton").Content = "다음";
            Text("FooterNote", "CHZZK Auto Category · v" + productVersion);
        }
        private void SelectOperation(SetupOperation operation)
        {
            Operation = operation;
            onWelcome = false;
            ShowPanel("OptionsPanel");
            bool remove = operation == SetupOperation.Remove;
            Find<CheckBox>("LaunchCheckBox").Visibility = remove ? Visibility.Collapsed : Visibility.Visible;
            Text("HeaderTitle", "CHZZK Auto Category " + (remove ? "제거" : maintenance ? "유지 관리" : upgrading ? "업데이트" : "설치"));
            Text("PageTitle", remove ? "프로그램을 제거할까요?" : maintenance ? "필요한 작업을 선택해 주세요" : upgrading ? "새 버전으로 업데이트합니다" : "설치할 폴더를 선택해 주세요");
            Text("PageDescription", remove ? "프로그램 파일을 제거하고 저장한 설정과 게임 규칙은 유지합니다." : maintenance ? "설치된 프로그램을 복구하거나 제거할 수 있습니다." : upgrading ? "기존 설치 위치를 사용하며 사용자 설정은 유지합니다." : "기본 위치를 사용하거나 다른 폴더를 선택할 수 있습니다.");
            Find<Button>("PrimaryButton").Content = remove ? "제거하기" : maintenance ? "복구하기" : upgrading ? "업데이트" : "설치하기";
            Find<Button>("BackButton").Visibility = hasWelcome ? Visibility.Visible : Visibility.Collapsed;
            Text("FooterNote", "CHZZK Auto Category · v" + productVersion);
        }
        private void Browse(object sender, RoutedEventArgs e)
        {
            using (var dialog = new Forms.FolderBrowserDialog { Description = "CHZZK Auto Category 설치 위치", SelectedPath = Find<TextBox>("InstallFolder").Text, ShowNewFolderButton = true })
            {
                var owner = new NativeOwner(new System.Windows.Interop.WindowInteropHelper(Window).Handle);
                if (dialog.ShowDialog(owner) == Forms.DialogResult.OK) Find<TextBox>("InstallFolder").Text = dialog.SelectedPath;
            }
        }
        private sealed class NativeOwner : Forms.IWin32Window
        {
            public IntPtr Handle { get; private set; }
            public NativeOwner(IntPtr handle) { Handle = handle; }
        }
        private void Primary(object sender, RoutedEventArgs e)
        {
            if (finished)
            {
                if (state.CanLaunch(Operation, LaunchSelected))
                {
                    try
                    {
                        Process.Start(new ProcessStartInfo(Path.Combine(InstallFolder, "ChzzkAutoCategory.exe"), "--after-install") { UseShellExecute = true, WorkingDirectory = InstallFolder });
                    }
                    catch (Exception ex)
                    {
                        Text("ResultDetail", "프로그램 실행에 실패했습니다. 시작 메뉴에서 실행해 주세요.\n" + ex.Message);
                        LaunchSelected = false;
                        Find<Button>("PrimaryButton").Content = "닫기";
                        return;
                    }
                }
                Window.Close();
                return;
            }
            if (Started || !string.IsNullOrEmpty(preflightError)) return;
            if (onWelcome)
            {
                SelectOperation(Operation);
                Find<TextBox>("InstallFolder").Focus();
                return;
            }
            try
            {
                string value = Find<TextBox>("InstallFolder").Text.Trim();
                if (!Path.IsPathRooted(value) || value.IndexOfAny(Path.GetInvalidPathChars()) >= 0 || value.Contains("\"")) throw new ArgumentException("전체 폴더 경로를 입력해 주세요.");
                value = Path.GetFullPath(value);
                if (value.TrimEnd('\\') == Path.GetPathRoot(value).TrimEnd('\\') || File.Exists(value)) throw new ArgumentException("드라이브 루트나 파일 대신 프로그램 전용 폴더를 선택해 주세요.");
                InstallFolder = value;
            }
            catch (Exception ex)
            {
                Text("FolderError", "설치 위치를 확인해 주세요. " + ex.Message);
                Find<TextBlock>("FolderError").Visibility = Visibility.Visible;
                return;
            }
            LaunchSelected = Find<CheckBox>("LaunchCheckBox").IsChecked == true;
            Started = true;
            ShowPanel("ProgressPanel");
            Text("ProgressTitle", Operation == SetupOperation.Remove ? "프로그램을 정리하고 있습니다" : Operation == SetupOperation.Repair ? "프로그램을 복구하고 있습니다" : "방송에 집중하세요");
            Text("ProgressDescription", Operation == SetupOperation.Remove ? "저장한 사용자 설정과 게임 규칙은\n다시 설치할 때 이어서 사용할 수 있습니다." : "실행 중인 게임을 감지하고\n치지직 카테고리를 자동으로 변경합니다.");
            Text("FooterNote", Operation == SetupOperation.Remove ? "제거 중입니다" : Operation == SetupOperation.Repair ? "복구 중입니다" : upgrading ? "업데이트 중입니다" : "설치 중입니다");
            Find<ProgressBar>("InstallProgress").IsIndeterminate = true;
            Find<Button>("BackButton").Visibility = Visibility.Collapsed;
            Find<Button>("PrimaryButton").Visibility = Visibility.Collapsed;
            start.Set();
        }
        private void RequestClose()
        {
            if (!Started || finished) Window.Close();
            else RequestCancellation();
        }
        private void RequestCancellation()
        {
            if (!cancelAllowed || state.CancellationRequested) return;
            if (Prompt("작업을 취소할까요?", "취소하면 Windows Installer가 진행한 변경을 되돌립니다. 롤백이 끝날 때까지 창을 닫지 마세요.", new[] { "계속 진행", "작업 취소" }, 0) != 1) return;
            state.RequestCancellation();
            SetCancelAllowed(false);
            Text("CurrentAction", "취소를 요청했습니다. 변경 사항을 되돌리는 중입니다.");
            Text("FooterNote", "롤백이 끝나면 창을 닫을 수 있습니다.");
        }
        public void SetCancelAllowed(bool allowed)
        {
            cancelAllowed = allowed && !state.CancellationRequested;
            Find<Button>("CancelButton").IsEnabled = cancelAllowed;
            Find<Button>("CloseButton").IsEnabled = cancelAllowed;
        }
        public void UpdateProgress(string action)
        {
            Find<ProgressBar>("InstallProgress").IsIndeterminate = state.Progress <= 0 && !state.CancellationRequested;
            Find<ProgressBar>("InstallProgress").Value = state.Progress * 100;
            Text("PercentLabel", Math.Round(state.Progress * 100) + "%");
            if (!string.IsNullOrEmpty(action) && !state.CancellationRequested) Text("CurrentAction", action);
        }
        public void Complete()
        {
            ShowWizard();
            finished = true;
            ShowPanel("ResultPanel");
            Find<ProgressBar>("InstallProgress").IsIndeterminate = false;
            Find<Button>("BackButton").Visibility = Visibility.Collapsed;
            Find<Button>("CancelButton").Visibility = Visibility.Collapsed;
            Find<Button>("CloseButton").IsEnabled = true;
            Find<Button>("PrimaryButton").Visibility = Visibility.Visible;
            string title, description;
            switch (state.Outcome)
            {
                case SetupOutcome.Success:
                    title = Operation == SetupOperation.Remove ? "프로그램 제거가 완료되었습니다" : Operation == SetupOperation.Repair ? "프로그램 복구가 완료되었습니다" : "설치가 완료되었습니다";
                    description = Operation == SetupOperation.Remove ? "저장한 설정과 게임 규칙은 유지했습니다. 다시 설치하면 이어서 사용할 수 있습니다." : "CHZZK Auto Category를 사용할 준비가 되었습니다.\n처음 실행하면 채널과 확장프로그램 연결을 안내합니다.";
                    break;
                case SetupOutcome.RebootRequired:
                    title = "다시 시작하면 준비가 끝납니다";
                    description = "설치는 완료되었지만 Windows를 다시 시작해야 합니다. 자동으로 재부팅하지 않습니다.";
                    break;
                case SetupOutcome.Canceled:
                    title = "작업을 취소했습니다";
                    description = "Windows Installer가 변경 사항을 되돌렸습니다. 필요할 때 MSI를 다시 실행해 주세요.";
                    break;
                default:
                    title = "작업을 완료하지 못했습니다";
                    description = "완료 결과를 확인하지 못했거나 설치 중 오류가 발생했습니다. 설치 로그를 확인한 뒤 다시 시도해 주세요.";
                    break;
            }
            bool success = state.Outcome == SetupOutcome.Success || state.Outcome == SetupOutcome.RebootRequired;
            Text("ResultTitle", title);
            Text("ResultDescription", description);
            Text("ResultGlyph", success ? "✓" : "!");
            Find<Border>("ResultGlyphBackground").Background = Brush(success ? "#FCEAE7" : "#F7EEEE");
            Text("ResultDetail", !success && !string.IsNullOrEmpty(logPath) ? "설치 로그\n" + logPath : Operation == SetupOperation.Remove ? "Chrome 확장프로그램은 Chrome에서 별도로 제거할 수 있습니다." : "설치 위치 · " + InstallFolder);
            Find<Button>("PrimaryButton").Content = success ? "완료" : "닫기";
            Text("FooterNote", state.Outcome == SetupOutcome.RebootRequired ? "Windows를 다시 시작해 주세요." : "CHZZK Auto Category · v" + productVersion);
            Find<Button>("PrimaryButton").Focus();
        }
        private void ShowPanel(string name)
        {
            foreach (string panel in new[] { "WelcomePanel", "OptionsPanel", "ProgressPanel", "ResultPanel" }) Find<FrameworkElement>(panel).Visibility = panel == name ? Visibility.Visible : Visibility.Collapsed;
        }
        private static SolidColorBrush Brush(string hex) { return new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex)); }

        // Engine prompts share the installer styling and preserve every MSI button choice.
        public int Prompt(string title, string message, string[] choices, int defaultIndex)
        {
            int selected = -1;
            var dialog = new Window { Owner = Window, Title = title, Width = 540, SizeToContent = SizeToContent.Height,
                MaxHeight = 650, WindowStartupLocation = WindowStartupLocation.CenterOwner, ResizeMode = ResizeMode.NoResize,
                WindowStyle = WindowStyle.None, AllowsTransparency = true, Background = Brushes.Transparent,
                FontFamily = Window.FontFamily, ShowInTaskbar = false };
            var stack = new StackPanel { Margin = new Thickness(26) };
            stack.Children.Add(new TextBlock { Text = title, FontSize = 18, FontWeight = FontWeights.SemiBold, Foreground = Brush("#292929"), TextWrapping = TextWrapping.Wrap });
            stack.Children.Add(new ScrollViewer { MaxHeight = 390, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Margin = new Thickness(0, 18, 0, 22), Content = new TextBlock { Text = message, TextWrapping = TextWrapping.Wrap, Foreground = Brush("#777777"), FontSize = 12 } });
            var buttons = new WrapPanel { HorizontalAlignment = HorizontalAlignment.Right };
            for (int i = 0; i < choices.Length; i++)
            {
                int index = i;
                var button = new Button { Content = choices[i], Style = (Style)Window.Resources[i == defaultIndex ? "PrimaryButton" : "SoftButton"],
                    MinWidth = 85, Margin = new Thickness(6, 0, 0, 0), IsDefault = i == defaultIndex };
                button.Click += (_, __) => { selected = index; dialog.Close(); };
                buttons.Children.Add(button);
            }
            stack.Children.Add(buttons);
            dialog.Content = new Border { Background = Brushes.White, CornerRadius = new CornerRadius(6),
                BorderBrush = Brush("#DDDDDD"), BorderThickness = new Thickness(1), Child = stack };
            // Do not silently turn Alt+F4 into permission to continue the installation.
            dialog.Closing += (_, e) => { if (selected < 0) e.Cancel = true; };
            dialog.ShowDialog();
            return selected;
        }
    }
}
