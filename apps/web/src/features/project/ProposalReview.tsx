import type { ProjectWorkspace, ProposalIssue, SlideSpec } from "../../api";
import { Icon } from "../../components/Icon";

/** Issues that changed a model proposal (everything the validator recorded). */
export const proposalIssueCount = (issues?: ProposalIssue[]) => issues?.length ?? 0;

/** Inspector note for the current slide: what the rules changed in the model's proposal. */
export function SlideProposalNote({ slide }: { slide?: SlideSpec }) {
  const issues = slide?.proposalIssues ?? [];
  if (!issues.length) return null;
  const fallback = issues.some((issue) => issue.code === "fallback" || issue.code === "missing-page");
  return (
    <details className="proposal-note">
      <summary>
        <Icon name="shield" size={14} />
        <span>{fallback ? "本页使用内置规划结果" : `已自动修正 ${issues.length} 处模型提议`}</span>
      </summary>
      <ul>{issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.message}</li>)}</ul>
      <small>规则负责页数、证据与数字；被修正的内容不会进入页面。</small>
    </details>
  );
}

/** Deck-level summary of proposal validation, grouped by page with a jump action. */
export function ProposalReviewPanel({ data, onJump }: { data: ProjectWorkspace; onJump: (slideId: string) => void }) {
  const validation = data.proposalValidation;
  const issues = validation?.issues ?? [];
  if (!validation || !issues.length) return null;
  const summary = validation.summary ?? {};
  const byPage = new Map<number | null, ProposalIssue[]>();
  for (const issue of issues) byPage.set(issue.position, [...(byPage.get(issue.position) ?? []), issue]);
  const pages = [...byPage.entries()].sort(([left], [right]) => (left ?? 0) - (right ?? 0));
  return (
    <details className="panel proposal-review">
      <summary>
        <span className="proposal-review-icon"><Icon name="shield" size={15} /></span>
        <span><b>已自动修正 {issues.length} 处模型提议</b><small>{summary.pages ?? data.slides.length} 页中 {summary.accepted ?? 0} 页直接采用 · {summary.repaired ?? 0} 页已修正 · {summary.fallback ?? 0} 页使用内置规划</small></span>
      </summary>
      <p>模型只负责文案与视觉建议；页数、角色顺序、证据编号和数字由规则把关。下面是被修改或拒绝的提议，可跳到对应页面复核。</p>
      <ul className="proposal-pages">
        {pages.map(([position, items]) => {
          const slide = data.slides.find((item) => item.position === position);
          return (
            <li key={String(position)}>
              <span className="proposal-page">{position ? `第 ${position} 页` : "全稿"}</span>
              <span className="proposal-messages">{[...new Set(items.map((item) => item.message))].map((message) => <span key={message}>{message}</span>)}</span>
              {slide && <button type="button" className="ghost btn-sm" onClick={() => onJump(slide.id)}>查看</button>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
