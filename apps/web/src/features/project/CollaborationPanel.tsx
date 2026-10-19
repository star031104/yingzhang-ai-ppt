import { useState } from "react";
import { addProjectMember, publishProject, recordProjectApproval } from "../../api";
import type { ProjectWorkspace } from "../../api";
import { Icon } from "../../components/Icon";

/** Advanced: members, final approval and secure publishing. */
export function CollaborationPanel({
  projectId,
  data,
  setStatus,
  refresh,
}: {
  projectId: string;
  data: ProjectWorkspace;
  setStatus: (status: string) => void;
  refresh: () => Promise<unknown>;
}) {
  const [memberName, setMemberName] = useState("");
  const active = (data.publications || []).filter((item) => item.status === "active");
  return (
    <details className="panel p1-studio collaboration-panel">
      <summary><span><b>协作、审批与发布</b><small>成员角色、最终审批和安全发布链接</small></span><i>高级</i></summary>
      <div className="p1-section">
        <b>成员与审批</b>
        <div className="p1-row"><input value={memberName} onChange={(event) => setMemberName(event.target.value)} placeholder="成员姓名或独立账号名称" aria-label="成员名称" /><button disabled={!memberName.trim()} onClick={async () => { await addProjectMember(projectId, memberName, "reviewer"); setMemberName(""); await refresh(); }}><Icon name="users" size={14} />添加审阅人</button></div>
        <div className="member-list">{(data.members || []).map((member) => <span key={member.id}>{member.name} · {member.role}</span>)}</div>
        <div className="approval-actions">
          <button onClick={async () => { try { await recordProjectApproval(projectId, "final", "changes_requested", "需要继续修改"); await refresh(); setStatus("已记录修改意见"); } catch (error) { setStatus(error instanceof Error ? error.message : "记录失败"); } }}>要求修改</button>
          <button className="primary" onClick={async () => { try { await recordProjectApproval(projectId, "final", "approved", "同意发布"); await refresh(); setStatus("最终审批已通过"); } catch (error) { setStatus(error instanceof Error ? error.message : "审批失败"); } }}>批准发布</button>
          <button onClick={async () => { try { const result = await publishProject(projectId); await refresh(); await navigator.clipboard?.writeText(`${location.origin}${result.url}`); setStatus("安全发布链接已创建并复制"); } catch (error) { setStatus(error instanceof Error ? error.message : "发布失败"); } }}><Icon name="link" size={14} />创建发布链接</button>
        </div>
        {active.map((item) => <a className="publication-link" key={item.id} href={`/api/v1/public/decks/${item.token}`} target="_blank" rel="noreferrer"><Icon name="external" size={14} />打开发布快照</a>)}
      </div>
    </details>
  );
}
