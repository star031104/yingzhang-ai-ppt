using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(root, "启动项目.cmd");
        if (!File.Exists(script))
        {
            MessageBox.Show("找不到启动项目.cmd。请将启动映章.exe 放在项目根目录中运行。", "映章启动器", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe",
                Arguments = "/k \"\"" + script + "\"\"",
                WorkingDirectory = root,
                UseShellExecute = true,
                WindowStyle = ProcessWindowStyle.Normal
            });
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show("无法打开启动窗口：" + ex.Message, "映章启动器", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

}
