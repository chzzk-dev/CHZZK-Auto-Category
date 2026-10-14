using WixToolset.Dtf.WindowsInstaller;

namespace Chzzk.Installer
{
    public static class CompletionAction
    {
        [CustomAction]
        public static ActionResult ReportCompleted(Session session)
        {
            // This immediate action runs only for the embedded UI and only after
            // InstallFinalize. This assembly has custom actions only, no embedded UI.
            using (var record = new Record(1))
            {
                record.FormatString = "CHZZK_SETUP_RESULT:[1]";
                record.SetInteger(1, session.GetMode(InstallRunMode.RebootAtEnd) ? 3010 : 0);
                session.Message(InstallMessage.Info, record);
            }
            return ActionResult.Success;
        }
    }
}
