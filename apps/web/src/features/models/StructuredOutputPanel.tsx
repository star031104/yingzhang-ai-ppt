import { useEffect, useState } from "react";

import { getStructuredOutputStats } from "../../api";
import type { StructuredOutputStat } from "../../api";

const PATH_LABELS: [keyof StructuredOutputStat["paths"], string][] = [
  ["strict", "严格结构"],
  ["json-mode", "JSON 模式"],
  ["repaired", "修复一次"],
  ["regex-fallback", "宽松兜底"],
  ["failed", "失败"],
];

const percent = (value: number) => `${Math.round(value * 100)}%`;

/** Per-model structured-output reliability, so fallbacks never hide a weak model. */
export function StructuredOutputPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [rows, setRows] = useState<StructuredOutputStat[] | null>(null);
  useEffect(() => {
    getStructuredOutputStats()
      .then((payload) => setRows(payload.models))
      .catch(() => setRows([]));
  }, [refreshKey]);
  if (!rows || rows.length === 0) return null;
  return (
    <div className="structured-output-panel">
      <div className="section-heading compact">
        <div>
          <h3>结构化输出可靠性</h3>
          <p>优先使用严格 JSON Schema；不合格时带校验错误修复一次，最后才宽松解析。</p>
        </div>
      </div>
      <table className="data-table" aria-label="结构化输出统计">
        <thead>
          <tr>
            <th>模型</th>
            <th>调用</th>
            <th>一次通过</th>
            {PATH_LABELS.map(([, label]) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.model} title={row.lastErrors.join("\n")}>
              <td>
                {row.model}
                {row.schemaUnsupported && <span className="badge">不支持 Schema</span>}
              </td>
              <td>{row.calls}</td>
              <td>{percent(row.firstTryRate)}</td>
              {PATH_LABELS.map(([key]) => (
                <td key={key}>{row.paths[key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
