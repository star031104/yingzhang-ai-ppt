import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { getPublicSession, loginPublic, logoutPublic, json } from "./api";
import type { PublicSession } from "./api";
import "./style.css";

const queryClient = new QueryClient();

function Entry() {
  const [session, setSession] = useState<PublicSession | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectionError, setConnectionError] = useState(false);

  useEffect(() => {
    getPublicSession()
      .then(setSession)
      .catch(() => setConnectionError(true));
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("正在进入映章工作台…");
    try {
      if (session?.setupRequired) await json("/auth/accounts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: data.get("name"), password: data.get("password"), claim_local_workspace: data.get("claim") === "on" }) });
      const nextSession = await loginPublic(String(data.get("name")), String(data.get("password")));
      queryClient.clear();
      setSession(nextSession);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败，请检查访问密码");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await logoutPublic();
    queryClient.clear();
    setSession(await getPublicSession());
  }

  if (connectionError) {
    return <div className="entry-loading"><span>映</span><p>本地服务暂时无法连接，请先启动项目。</p><button onClick={() => window.location.reload()}>重新连接</button></div>;
  }
  if (!session) {
    return <div className="entry-loading"><span>映</span><p>正在打开映章…</p></div>;
  }
  if ((session.publicMode || session.privateMode) && !session.authenticated) {
    return (
      <main className="login-page">
        <section className="login-story">
          <div className="login-brand"><span>映</span><b>映章</b></div>
          <p className="kicker">协作测试空间</p>
          <h1>把材料变成<br/><em>清楚、可信、好看的演示</em></h1>
          <p>你可以创建项目、选择已安装技能、生成代表样张、微调页面，并下载 HTML、PPTX 与 PDF。</p>
          <div className="login-points"><span>来源可追溯</span><span>项目可继续编辑</span><span>成果可下载</span></div>
        </section>
        <section className="login-card">
          <span className="login-step">{session.privateMode ? "独立账号" : "受邀测试"}</span>
          <h2>{session.setupRequired ? "设置首个管理员账号" : "进入工作台"}</h2>
          <p>{session.privateMode ? "使用独立账号登录，项目和经验按账号隔离。首次管理员设置请从服务器本机打开。" : "请输入你的称呼和邀请人提供的访问密码。"}</p>
          <form onSubmit={login}>
            <label>你的称呼<input name="name" required minLength={2} maxLength={30} placeholder="例如：林晓" autoComplete="name"/></label>
            <label>访问密码<input name="password" required minLength={session.setupRequired ? 12 : 1} maxLength={200} type="password" placeholder="请输入密码" autoComplete="current-password"/></label>
            {session.setupRequired && <label><input name="claim" type="checkbox" />将已有本机项目与经验交给此管理员账号</label>}
            <button disabled={busy}>{busy ? "正在验证…" : "进入映章 →"}</button>
          </form>
          {message && <div className="login-message">{message}</div>}
          <small>模型密钥和管理设置不会向测试者开放。</small>
        </section>
      </main>
    );
  }
  return <App session={session} onLogout={logout}/>;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><QueryClientProvider client={queryClient}><Entry/></QueryClientProvider></React.StrictMode>,
);
