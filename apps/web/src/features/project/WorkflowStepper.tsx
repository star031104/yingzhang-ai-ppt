import type { ProjectWorkspace, QualityReport } from "../../api";
import { Icon } from "../../components/Icon";

export type WorkflowStep = "create" | "sources" | "outline" | "generate" | "edit" | "quality" | "export";
type StepState = "done" | "current" | "warning" | "optional" | "todo";

const LABELS: Record<WorkflowStep, string> = {
  create: "新建",
  sources: "材料",
  outline: "大纲",
  generate: "生成",
  edit: "编辑",
  quality: "质量",
  export: "导出",
};

export function workflowStates(data: ProjectWorkspace, quality: QualityReport | null, busy: boolean): Record<WorkflowStep, StepState> {
  const slides = data.slides?.length ?? 0;
  const gates = data.gates?.enabled ? data.gates : null;
  const outlineDone = slides > 0 && (!gates || gates.outline === "approved");
  const generated = Boolean(data.previewAvailable);
  const qualityState: StepState = quality ? (quality.passed ? "done" : "warning") : generated ? "current" : "todo";
  return {
    create: "done",
    sources: (data.sources?.length ?? 0) > 0 ? "done" : "optional",
    outline: outlineDone ? "done" : "current",
    generate: generated ? "done" : outlineDone || busy ? "current" : "todo",
    edit: generated ? "done" : "todo",
    quality: qualityState,
    export: generated && quality?.passed ? "current" : "todo",
  };
}

export function WorkflowStepper({
  states,
  onStep,
}: {
  states: Record<WorkflowStep, StepState>;
  onStep: (step: WorkflowStep) => void;
}) {
  const steps = Object.keys(LABELS) as WorkflowStep[];
  return (
    <ol className="workflow-stepper" aria-label="创作流程">
      {steps.map((step, index) => {
        const state = states[step];
        return (
          <li key={step} className={`step-${state}`}>
            <button
              type="button"
              onClick={() => onStep(step)}
              disabled={step === "create"}
              aria-label={`${LABELS[step]}：${{ done: "已完成", current: "进行中", warning: "需要处理", optional: "可选", todo: "未开始" }[state]}`}
            >
              <span className="step-dot">
                {state === "done" ? <Icon name="check" size={11} strokeWidth={2.5} /> : state === "warning" ? "!" : index + 1}
              </span>
              <span className="step-label">{LABELS[step]}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
