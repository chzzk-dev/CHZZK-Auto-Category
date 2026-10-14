using System;
using Chzzk.Installer;

internal static class StateTests
{
    static int checks;
    static void Check(bool condition, string name)
    {
        if (!condition) throw new Exception(name);
        checks++;
    }
    static void Main()
    {
        var state = new InstallState();
        Check(!state.CanLaunch(SetupOperation.Install, true), "unknown result cannot launch");
        state.ProgressRecord(new[] { 0, 100, 0, 0 });
        state.ProgressRecord(new[] { 2, 50 });
        Check(Math.Abs(state.Progress - 0.125) < 0.001, "script generation progress");
        state.ProgressRecord(new[] { 0, 100, 0, 1 });
        state.ProgressRecord(new[] { 1, 10, 1 });
        state.ActionData();
        Check(Math.Abs(state.Progress - 0.324) < 0.001, "action data advances progress");
        state.ActionStart(); state.ActionData();
        Check(Math.Abs(state.Progress - 0.324) < 0.001, "new action disables previous action ticks");
        state.ProgressRecord(new[] { 2, 1000 });
        Check(state.Progress < 1, "100 percent requires committed completion");
        state.ProgressRecord(new[] { 0, 100, 1, 1 });
        state.ProgressRecord(new[] { 2, 50 });
        Check(state.Progress < 0.99, "rollback reset is not completion");
        state.ProgressRecord(new[] { 0 }); state.ProgressRecord(new[] { 2 });
        Check(state.Outcome == SetupOutcome.Unknown, "malformed progress is not success");
        state.RequestCancellation();
        Check(state.TakeCancellation() && !state.TakeCancellation(), "cancel sent once");
        foreach (int code in new[] { 1602, 1603, 1618, 3010, 1641 })
        {
            state.Finish(code);
            Check(!state.CanLaunch(SetupOperation.Install, true), "non-success never launches: " + code);
        }
        state.Finish(0);
        Check(state.CanLaunch(SetupOperation.Install, true), "successful install may launch");
        Check(state.CanLaunch(SetupOperation.Repair, true), "successful repair may launch");
        Check(!state.CanLaunch(SetupOperation.Remove, true), "removal never launches");
        Check(!state.CanLaunch(SetupOperation.Install, false), "unchecked launch respected");
        Check(state.Progress == 1, "commit completion reaches 100 percent");
        Console.WriteLine(checks + " installer state assertions passed.");
    }
}
