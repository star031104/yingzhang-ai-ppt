import { jobPagePreviewUrl } from "../api";
import type { ProjectJob } from "../api";

const STATUS_LABEL = {
  pending: "等待",
  running: "生成中",
  ready: "完成",
  failed: "失败",
  cancelled: "已取消",
} as const;

export function JobPageProgress({ job }: { job: ProjectJob }) {
  const pages = job.checkpoint.pages || [];
  if (!pages.length) return null;
  const ready = pages.filter((page) => page.status === "ready").length;
  const failed = pages.filter((page) => page.status === "failed").length;

  return (
    <section className="page-job-progress" aria-label="逐页生成进度">
      <div className="page-job-summary">
        <b>逐页生成</b>
        <span>{ready}/{pages.length} 页完成{failed ? ` · ${failed} 页待重试` : ""}</span>
      </div>
      <div className="page-job-grid">
        {pages.map((page) => (
          <div
            className={`page-job-item ${page.status}`}
            key={page.slideId}
            title={page.error || `第 ${page.position} 页：${STATUS_LABEL[page.status]}`}
          >
            {page.status === "ready" && (
              <img src={jobPagePreviewUrl(job.id, page.slideId)} alt={`第 ${page.position} 页预览`} />
            )}
            <b>{String(page.position).padStart(2, "0")}</b>
            <span>{STATUS_LABEL[page.status]}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
