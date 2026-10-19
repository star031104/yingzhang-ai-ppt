import { useEffect, useState } from "react";
import { getResearchEvaluation, listResearchEvaluations, runResearchEvaluation } from "../../api";
import type { EvaluationKind, ResearchEvaluationRun } from "../../api";
import "./evaluation-panel.css";

const KIND_LABELS: Record<EvaluationKind, string> = {
  ppteval: "三维评分（PPTEval）",
  quiz: "信息保留测验",
  render: "PPTX 实际页面复核",
};
const DIMENSIONS = [
  ["content", "内容"],
  ["design", "设计"],
  ["coherence", "连贯"],
] as const;
const MODE_LABELS: Record<string, string> = {
  rule: "规则评估",
  text: "文本模型评审",
  vision: "视觉模型评审",
  "vision+text": "视觉与文本模型评审",
  deterministic: "图像规则检查",
};
const RENDER_STATUS: Record<string, string> = {
  "no-export": "尚无 PPTX 导出，请先导出后再复核实际页面",
  unavailable: "本机未找到 LibreOffice，无法渲染 PPTX 页面",
  failed: "PPTX 渲染失败，请检查导出文件",
};

type SlideRef = { id: string; position: number };
type PageIssue = { position: number; slideId?: string; dimension: string; message: string; suggestion?: string };

function collectIssues(run: ResearchEvaluationRun): PageIssue[] {
  const issues: PageIssue[] = [];
  for (const slide of run.ppteval?.slides ?? []) {
    for (const issue of slide.issues) {
      issues.push({ position: slide.position, slideId: slide.slideId, dimension: issue.dimension, message: issue.message, suggestion: issue.suggestion });
    }
  }
  for (const page of run.render?.pages ?? []) {
    for (const issue of page.issues) {
      issues.push({ position: page.page, slideId: page.slideId, dimension: "render", message: issue.message, suggestion: issue.suggestion });
    }
  }
  return issues.sort((left, right) => left.position - right.position);
}

const DIMENSION_TAGS: Record<string, string> = { content: "内容", design: "设计", coherence: "连贯", render: "实际页面" };

export function EvaluationPanel({
  projectId,
  slides = [],
  onJumpToSlide,
}: {
  projectId: string;
  slides?: SlideRef[];
  onJumpToSlide?: (slideId: string, position: number) => void;
}) {
  const [kinds, setKinds] = useState<EvaluationKind[]>(["ppteval", "quiz"]);
  const [run, setRun] = useState<ResearchEvaluationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    listResearchEvaluations(projectId)
      .then(async (runs) => {
        const latest = runs.find((item) => item.status === "completed") ?? runs[0];
        if (!latest) return;
        const detail = await getResearchEvaluation(projectId, latest.id);
        if (active) setRun(detail);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [projectId]);

  const toggle = (kind: EvaluationKind) =>
    setKinds((current) => (current.includes(kind) ? current.filter((item) => item !== kind) : [...current, kind]));

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      setRun(await runResearchEvaluation(projectId, kinds));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "评测失败");
    } finally {
      setBusy(false);
    }
  };

  const jump = (issue: PageIssue) => {
    const slideId = issue.slideId ?? slides.find((slide) => slide.position === issue.position)?.id;
    if (slideId && onJumpToSlide) onJumpToSlide(slideId, issue.position);
  };

  const issues = run ? collectIssues(run) : [];
  const quiz = run?.quiz;
  const missedQuestions = quiz?.questions.filter((item) => !item.correct) ?? [];

  return (
    <section className="eval-panel" aria-label="研究级评测">
      <header className="eval-header">
        <div>
          <b>研究级评测</b>
          <small>PPTEval 三维评分 · 材料信息保留测验 · 导出页面复核</small>
        </div>
        {run?.stale && <span className="eval-badge eval-badge-stale">内容已修改，结果已过期</span>}
        {run && !run.stale && run.status === "completed" && <span className="eval-badge eval-badge-current">与当前内容一致</span>}
      </header>

      <div className="eval-controls">
        {(Object.keys(KIND_LABELS) as EvaluationKind[]).map((kind) => (
          <label key={kind} className="eval-kind">
            <input type="checkbox" checked={kinds.includes(kind)} onChange={() => toggle(kind)} disabled={busy} />
            {KIND_LABELS[kind]}
          </label>
        ))}
        <button type="button" className="eval-run primary btn-sm" disabled={busy || kinds.length === 0} onClick={start}>
          {busy ? "评测中…" : "运行评测"}
        </button>
      </div>
      {error && <p className="eval-error" role="alert">{error}</p>}
      {run?.status === "failed" && <p className="eval-error" role="alert">{run.error || "评测失败"}</p>}
      {run?.status === "interrupted" && <p className="eval-error" role="alert">上次评测被中断，请重新运行</p>}

      {run?.ppteval && (
        <div className="eval-scores">
          {DIMENSIONS.map(([key, label]) => {
            const value = run.ppteval!.deck[key];
            return (
              <div key={key} className={`eval-score eval-score-${key}`}>
                <span className="eval-score-label">{label}</span>
                <strong className="eval-score-value">{value.score.toFixed(1)}<i>/5</i></strong>
                <p className="eval-score-rationale">{value.rationale}</p>
                {!!value.suggestions?.length && (
                  <ul className="eval-suggestions">
                    {value.suggestions.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                )}
              </div>
            );
          })}
          <small className="eval-mode">{MODE_LABELS[run.ppteval.mode] || run.ppteval.mode}</small>
        </div>
      )}

      {quiz && (
        <div className="eval-quiz">
          {quiz.status === "completed" ? (
            <>
              <div className="eval-quiz-summary">
                <span><b>{quiz.retention ?? "—"}%</b>信息保留率</span>
                <span><b>{quiz.detailRetention ?? "—"}%</b>细节题</span>
                <span><b>{quiz.conceptRetention ?? "—"}%</b>概念题</span>
                <small>{quiz.questions.length} 题 · {quiz.generator === "llm" ? "模型出题" : "规则出题"} · {quiz.answerer === "llm" ? "模型仅凭页面作答" : "页面文字匹配作答"}</small>
              </div>
              {!!quiz.missingFacts.length && (
                <div className="eval-missing">
                  <b>材料中的重要事实未出现在演示中</b>
                  <ul>
                    {quiz.missingFacts.slice(0, 5).map((fact) => (
                      <li key={fact.claim}>{fact.claim}<em>缺少 {fact.missingValues.join("、")}</em></li>
                    ))}
                  </ul>
                </div>
              )}
              {!!missedQuestions.length && (
                <details className="eval-trace">
                  <summary>查看未答对的 {missedQuestions.length} 道题</summary>
                  <ol>
                    {missedQuestions.map((item) => (
                      <li key={item.id}>
                        <span className="eval-trace-type">{item.type === "detail" ? "细节" : "概念"}</span>
                        <p>{item.question}</p>
                        <small>材料答案：{item.expected}；页面作答：{item.answer}</small>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </>
          ) : (
            <p className="eval-note">{quiz.message || "未生成测验题目"}</p>
          )}
        </div>
      )}

      {run?.render && run.render.status !== "completed" && (
        <p className="eval-note">{RENDER_STATUS[run.render.status] || run.render.message}</p>
      )}
      {run?.render?.status === "completed" && run.exportMatchesCurrent === false && (
        <p className="eval-note">页面复核基于较早的 PPTX 导出，重新导出后结果更准确</p>
      )}

      {!!issues.length && (
        <ul className="eval-issues" aria-label="逐页问题">
          {issues.slice(0, 30).map((issue, index) => (
            <li key={`${issue.position}-${issue.dimension}-${index}`} className="eval-issue">
              <span className="eval-issue-page">第 {issue.position} 页</span>
              <span className="eval-issue-tag">{DIMENSION_TAGS[issue.dimension] || issue.dimension}</span>
              <span className="eval-issue-text"><b>{issue.message}</b>{issue.suggestion && <small>{issue.suggestion}</small>}</span>
              {onJumpToSlide && (
                <button type="button" className="eval-jump ghost btn-sm" onClick={() => jump(issue)}>跳到该页</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {run?.status === "completed" && !issues.length && run.ppteval && <p className="eval-note">未发现逐页问题</p>}
    </section>
  );
}
