using System;

namespace Chzzk.Installer
{
    public enum SetupOperation { Install, Repair, Remove }
    public enum SetupOutcome { Unknown, Success, Canceled, Failed, RebootRequired }

    // Independent of WPF and MSI handles so result and progress rules can be tested.
    public sealed class InstallState
    {
        private long total, completed, actionStep;
        private bool forward = true, actionData;
        private int phase;
        public double Progress { get; private set; }
        public bool CancellationRequested { get; private set; }
        public bool CancellationSent { get; private set; }
        public SetupOutcome Outcome { get; private set; }
        public void RequestCancellation() { CancellationRequested = true; }
        public bool TakeCancellation()
        {
            if (!CancellationRequested || CancellationSent) return false;
            CancellationSent = true;
            return true;
        }
        public void Finish(int exitCode)
        {
            switch (exitCode)
            {
                case 0: Outcome = SetupOutcome.Success; Progress = 1; break;
                case 3010:
                case 1641: Outcome = SetupOutcome.RebootRequired; Progress = 1; break;
                case 1602: Outcome = SetupOutcome.Canceled; break;
                default: Outcome = SetupOutcome.Failed; break;
            }
        }
        public bool CanLaunch(SetupOperation operation, bool launchSelected)
        {
            return Outcome == SetupOutcome.Success && operation != SetupOperation.Remove && launchSelected;
        }
        public void ActionStart() { actionData = false; }
        public void ActionData()
        {
            if (actionData) Advance(actionStep);
        }
        public void ProgressRecord(int[] fields)
        {
            if (fields == null || fields.Length == 0) return;
            switch (fields[0])
            {
                case 0:
                    if (fields.Length < 4) return;
                    phase++;
                    total = Math.Max(0, fields[1]);
                    forward = fields[2] == 0;
                    completed = forward ? 0 : total;
                    actionData = false;
                    break;
                case 1:
                    if (fields.Length < 3) return;
                    actionStep = Math.Max(0, fields[1]);
                    actionData = fields[2] != 0;
                    break;
                case 2:
                    if (fields.Length < 2) return;
                    Advance(fields[1]);
                    return;
                case 3:
                    if (fields.Length < 2) return;
                    total = Math.Max(0, total + fields[1]);
                    break;
            }
            UpdateProgress();
        }
        private void Advance(long ticks)
        {
            completed += forward ? ticks : -ticks;
            UpdateProgress();
        }
        private void UpdateProgress()
        {
            double fraction = total > 0 ? Math.Max(0, Math.Min(1, (double)completed / total)) : 0;
            // MSI script generation and execution are separate progress phases.
            // Later resets (including rollback) must not imply a successful finish.
            Progress = phase <= 1 ? fraction * 0.25 : 0.25 + fraction * 0.74;
        }
    }
}
