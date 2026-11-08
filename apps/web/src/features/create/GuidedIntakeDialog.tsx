import { useMemo, useState } from "react";

import type { GuidedIntake, IntakeQuestion } from "../../api";

type Answers = Record<string, unknown>;

function initialAnswers(intake: GuidedIntake): Answers {
  const answers: Answers = {};
  for (const phase of intake.phases) for (const question of phase.questions) answers[question.id] = question.suggested;
  return answers;
}

function Field({ question, value, onChange }: { question: IntakeQuestion; value: unknown; onChange: (value: unknown) => void }) {
  if (question.type === "multi") {
    const selected = new Set(Array.isArray(value) ? (value as string[]) : []);
    if (!question.options?.length) return <small className="field-help">{question.why}</small>;
    return (
      <div className="intake-multi" role="group" aria-label={question.label}>
        {question.options.map((option) => (
          <label key={option.value} className="check">
            <input
              type="checkbox"
              checked={selected.has(option.value)}
              onChange={() => {
                const next = new Set(selected);
                if (next.has(option.value)) next.delete(option.value);
                else next.add(option.value);
                onChange([...next]);
              }}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    );
  }
  if (question.type === "choice") {
    return (
      <select aria-label={question.label} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)}>
        {question.options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    );
  }
  return (
    <input
      aria-label={question.label}
      type={question.type === "number" ? "number" : "text"}
      value={String(value ?? "")}
      onChange={(event) => onChange(question.type === "number" ? Number(event.target.value) : event.target.value)}
    />
  );
}

/** Five short phases before generation; every answer is pre-filled from the request and materials. */
export function GuidedIntakeDialog({
  intake,
  busy,
  onConfirm,
  onCancel,
}: {
  intake: GuidedIntake;
  busy: boolean;
  onConfirm: (answers: Answers) => void;
  onCancel: () => void;
}) {
  const [answers, setAnswers] = useState<Answers>(() => initialAnswers(intake));
  const [step, setStep] = useState(0);
  const phase = intake.phases[step];
  const last = step === intake.phases.length - 1;
  const progress = useMemo(() => `${step + 1} / ${intake.phases.length}`, [step, intake.phases.length]);
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal intake-dialog panel" role="dialog" aria-modal="true" aria-label="引导式创建">
        <header>
          <ol className="intake-steps">
            {intake.phases.map((item, index) => (
              <li key={item.id} className={index === step ? "active" : index < step ? "done" : ""}>{item.title}</li>
            ))}
          </ol>
          <small>{progress} · {phase.hint}</small>
        </header>
        <div className="intake-questions">
          {phase.questions.map((question) => (
            <label key={question.id} className="intake-question">
              <b>{question.label}</b>
              <Field question={question} value={answers[question.id]} onChange={(value) => setAnswers((current) => ({ ...current, [question.id]: value }))} />
              {question.why && question.type !== "multi" && <small className="field-help">{question.why}</small>}
            </label>
          ))}
        </div>
        <footer className="intake-actions">
          <button type="button" className="ghost" onClick={onCancel} disabled={busy}>取消</button>
          {step > 0 && <button type="button" className="ghost" onClick={() => setStep(step - 1)} disabled={busy}>上一步</button>}
          {!last && <button type="button" className="ghost" onClick={() => onConfirm(answers)} disabled={busy}>全部按建议生成</button>}
          {last
            ? <button type="button" className="primary" onClick={() => onConfirm(answers)} disabled={busy}>确认并开始生成</button>
            : <button type="button" className="primary" onClick={() => setStep(step + 1)} disabled={busy}>下一步</button>}
        </footer>
      </div>
    </div>
  );
}
