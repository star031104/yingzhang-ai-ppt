import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getPublicSession, json } from "../../api";

export function AccountPanel() {
  const session = useQuery({ queryKey: ["account-session"], queryFn: getPublicSession });
  const accounts = useQuery({ queryKey: ["private-accounts"], queryFn: () => json<{ id: string; name: string; enabled: boolean }[]>("/auth/accounts"), enabled: !!session.data?.privateMode && session.data?.role === "admin" });
  const [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  async function send(url: string, body: unknown) {
    setBusy(true);
    try { await json(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); if (url === "/auth/password") { window.location.reload(); return; } await accounts.refetch(); setMessage("已保存。"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "操作失败"); }
    finally { setBusy(false); }
  }
  if (!session.data?.privateMode) return <div className="panel"><h3>独立账号部署</h3><p>当前为本机单人模式。如需多人各自培养助手，可在部署配置中开启独立账号模式，再从服务器本机完成首次管理员设置。</p></div>;
  return <div className="panel"><h3>我的独立账号</h3><p>当前账号：{session.data.name}。项目与个人经验按账号隔离。</p>{message && <p role="status">{message}</p>}
    <form onSubmit={async event => { event.preventDefault(); const form = new FormData(event.currentTarget); await send("/auth/password", { current_password: form.get("current"), new_password: form.get("password") }); }}>
      <label>当前密码<input type="password" name="current" required autoComplete="current-password" /></label>
      <label>新密码<input type="password" name="password" required minLength={12} maxLength={200} autoComplete="new-password" /></label><button disabled={busy}>更新密码并使旧登录失效</button>
    </form>
    {session.data.role === "admin" && <><h4>创建独立成员账号</h4><form onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); void send("/auth/accounts", { name: form.get("name"), password: form.get("password") }); }}>
      <label>账号名称<input name="name" minLength={2} maxLength={30} required /></label><label>初始密码<input name="password" type="password" minLength={12} maxLength={200} required autoComplete="new-password" /></label><button disabled={busy}>创建账号</button>
    </form>{accounts.data?.map(account => <p key={account.id}>{account.name} · {account.enabled ? "启用" : "停用"} {account.name !== session.data.name && account.enabled && <button disabled={busy} onClick={() => void send(`/auth/accounts/${account.id}/disable`, {})}>停用账号</button>}</p>)}</>}
  </div>;
}
