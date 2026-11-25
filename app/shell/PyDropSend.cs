// Petit relais lancé par le menu Windows « Envoyer avec PyDrop ».
// Il transmet les chemins à PyDrop et le démarre s'il n'est pas ouvert.
// Compilation : csc /target:winexe /win32icon:pydrop.ico /out:PyDropSend.exe PyDropSend.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;

class PyDropSend
{
    static string Folder { get { return AppDomain.CurrentDomain.BaseDirectory; } }

    static string Json(string[] paths)
    {
        var sb = new StringBuilder("{\"paths\":[");
        for (int i = 0; i < paths.Length; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append('"');
            foreach (char c in paths[i])
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c < 32) sb.Append("\\u").Append(((int)c).ToString("x4"));
                else sb.Append(c);
            }
            sb.Append('"');
        }
        return sb.Append("]}").ToString();
    }

    static bool Post(string json)
    {
        try
        {
            string portFile = Path.Combine(Folder, "port.txt");
            if (!File.Exists(portFile)) return false;
            string port = File.ReadAllText(portFile).Trim();
            var req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/local/send");
            req.Method = "POST";
            req.Timeout = 3000;
            req.Proxy = null;
            req.ContentType = "application/json";
            req.Headers["X-PyDrop-Local"] = "1";
            byte[] body = Encoding.UTF8.GetBytes(json);
            using (var s = req.GetRequestStream()) s.Write(body, 0, body.Length);
            using (var r = (HttpWebResponse)req.GetResponse()) return r.StatusCode == HttpStatusCode.OK;
        }
        catch (Exception)
        {
            return false;
        }
    }

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 0) return 0;
        string json = Json(args);
        if (Post(json)) return 0;

        // PyDrop n'est pas ouvert : un seul relais le démarre, les autres attendent
        using (var starter = new Mutex(false, "PyDropSendStarter"))
        {
            bool owner = false;
            try { owner = starter.WaitOne(0); } catch (AbandonedMutexException) { owner = true; }
            if (owner)
            {
                try
                {
                    string exe = File.ReadAllText(Path.Combine(Folder, "main.txt")).Trim();
                    Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true });
                }
                catch (Exception) { return 1; }
            }
            for (int i = 0; i < 90; i++)
            {
                Thread.Sleep(500);
                if (Post(json)) return 0;
            }
        }
        return 1;
    }
}
