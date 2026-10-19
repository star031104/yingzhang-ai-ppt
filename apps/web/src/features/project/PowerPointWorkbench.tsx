import { useEffect, useState } from "react";
import {
  blindEvaluationUrl,
  editImportedPowerPointObject,
  generateNarration,
  getProjectStorage,
  importedPowerPointExportUrl,
  importPowerPoint,
  runProfessionalEvaluation,
  setPowerPointEffects,
} from "../../api";
import type { ProjectWorkspace, SlideSpec } from "../../api";

const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(1)} ${units[unit]}`;
};

/** Advanced: transitions, narration, imported PPTX round-trip, evaluation and storage. */
export function PowerPointWorkbench({
  projectId,
  data,
  current,
  busy,
  setBusy,
  setStatus,
  refresh,
}: {
  projectId: string;
  data: ProjectWorkspace;
  current?: SlideSpec;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  setStatus: (status: string) => void;
  refresh: () => Promise<unknown>;
}) {
  const [pptTransition, setPptTransition] = useState("fade"),
    [pptAnimation, setPptAnimation] = useState("none"),
    [importedSlideIndex, setImportedSlideIndex] = useState(1),
    [importedObjectId, setImportedObjectId] = useState(""),
    [importedObjectValue, setImportedObjectValue] = useState(""),
    [storageReport, setStorageReport] = useState<Awaited<ReturnType<typeof getProjectStorage>> | null>(null);
  const importedSlide = data.importedPowerPoint?.analysis.slides.find((slide) => slide.position === importedSlideIndex);
  const importedEditableObjects = (importedSlide?.objects || []).filter((item) => item.editable);
  useEffect(() => {
    const selected = importedEditableObjects.find((item) => item.id === importedObjectId) || importedEditableObjects[0];
    setImportedObjectId(selected?.id ?? "");
    setImportedObjectValue(selected?.text ?? "");
  }, [importedSlideIndex, data.importedPowerPoint?.version]);
  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true);
    try { await action(); }
    catch (error) { setStatus(error instanceof Error ? error.message : failure); }
    finally { setBusy(false); }
  }
  const latestRun = data.evaluationRuns?.[0];
  const excluded = latestRun ? (latestRun.metrics.fixedCasesNotApplicable ?? 0) + (latestRun.metrics.fixedCasesNotVerified ?? 0) : 0;
  return (
    <details className="panel p2-studio">
      <summary><span><b>PowerPoint 深度工作台</b><small>转场动画、旁白、导入现有 PPTX 续编与专业评测</small></span><i>高级</i></summary>
      <div className="p2-block">
        <b>当前页演示效果</b>
        <div className="p2-controls">
          <select value={pptTransition} onChange={(event) => setPptTransition(event.target.value)} aria-label="转场">
            <option value="none">无转场</option><option value="fade">淡化</option><option value="push">推进</option><option value="wipe">擦除</option>
          </select>
          <select value={pptAnimation} onChange={(event) => setPptAnimation(event.target.value)} aria-label="对象动画">
            <option value="none">无对象动画</option><option value="fade">主对象淡入</option>
          </select>
          <button disabled={busy || !current} onClick={() => run(async () => {
            if (!current) return;
            await setPowerPointEffects(projectId, current.id, pptTransition, pptAnimation);
            await refresh();
            setStatus("当前页转场与动画已写入 PowerPoint 设置");
          }, "演示效果保存失败")}>保存效果</button>
        </div>
        <div className="partial-actions">
          <button disabled={busy || !current} onClick={() => run(async () => { if (!current) return; const result = await generateNarration(projectId, current.id); await refresh(); setStatus(`已生成当前页旁白，预计 ${result.totalSeconds} 秒`); }, "旁白生成失败")}>生成当前页旁白</button>
          <button disabled={busy} onClick={() => run(async () => { const result = await generateNarration(projectId); await refresh(); setStatus(`已生成全稿旁白，预计 ${Math.ceil(result.totalSeconds / 60)} 分钟`); }, "全稿旁白生成失败")}>生成全稿旁白</button>
        </div>
      </div>
      <div className="p2-block">
        <b>导入现有 PPTX 继续编辑</b>
        <label className="p2-upload"><input type="file" accept=".pptx" disabled={busy} onChange={(event) => {
          const input = event.currentTarget, file = input.files?.[0];
          if (!file) return;
          void run(async () => {
            setStatus("正在读取现有 PPTX 的母版、动画和对象…");
            try {
              await importPowerPoint(projectId, file);
              setImportedSlideIndex(1); setImportedObjectId("");
              await refresh();
              setStatus("PPTX 已导入，可按对象继续编辑");
            } finally { input.value = ""; }
          }, "PPTX 导入失败");
        }} /><span>选择 PPTX</span></label>
        {data.importedPowerPoint && <>
          <div className="fidelity-strip">
            <span>{data.importedPowerPoint.analysis.slideCount} 页</span><span>{data.importedPowerPoint.analysis.masterCount} 个母版</span><span>{data.importedPowerPoint.analysis.layoutCount} 个版式</span><span>{data.importedPowerPoint.analysis.animationSlides} 页动画</span><span>{data.importedPowerPoint.analysis.transitionSlides} 页转场</span>
          </div>
          <div className="p2-object-editor">
            <select value={importedSlideIndex} onChange={(event) => setImportedSlideIndex(Number(event.target.value))} aria-label="导入页面">{data.importedPowerPoint.analysis.slides.map((slide) => <option key={slide.position} value={slide.position}>第 {slide.position} 页 · {slide.title || "未命名"}</option>)}</select>
            <select value={importedObjectId} onChange={(event) => { const id = event.target.value; setImportedObjectId(id); setImportedObjectValue(importedEditableObjects.find((item) => item.id === id)?.text || ""); }} aria-label="可编辑对象">{importedEditableObjects.map((item) => <option key={item.id} value={item.id}>{item.name || `对象 ${item.id}`}</option>)}</select>
            <textarea rows={3} value={importedObjectValue} onChange={(event) => setImportedObjectValue(event.target.value)} placeholder="选择可编辑文字对象" />
            <button className="primary" disabled={busy || !importedObjectId} onClick={() => run(async () => { await editImportedPowerPointObject(projectId, importedSlideIndex, importedObjectId, importedObjectValue); await refresh(); setStatus("对象文字已更新，主题、母版、动画和转场保持不变"); }, "对象修改失败")}>保存对象修改</button>
          </div>
          <a className="publication-link" href={importedPowerPointExportUrl(projectId)}>导出高保真往返 PPTX</a>
        </>}
      </div>
      <div className="p2-block">
        <b>固定测试集与双盲评审</b>
        <div className="evaluation-summary">
          <span><b>{data.modelUsage?.inputTokens == null ? "未知" : data.modelUsage.inputTokens.toLocaleString()}</b>输入 tokens</span>
          <span><b>{data.modelUsage?.outputTokens == null ? "未知" : data.modelUsage.outputTokens.toLocaleString()}</b>输出 tokens</span>
          <span><b>{data.modelUsage?.requests ?? 0}</b>次模型请求</span>
        </div>
        <small className="field-help">已报告 {data.modelUsage?.reportedRequests ?? 0} 次；未返回 token 统计 {data.modelUsage?.unreportedRequests ?? 0} 次。未配置模型价格，因此不显示费用。</small>
        <div className="partial-actions">
          <button disabled={busy} onClick={() => run(async () => { const result = await runProfessionalEvaluation(projectId); await refresh(); const skipped = (result.metrics.fixedCasesNotApplicable ?? 0) + (result.metrics.fixedCasesNotVerified ?? 0); setStatus(`专业评测已完成：适用测试 ${result.metrics.fixedCasesPassed}/${result.metrics.fixedCasesTotal}${skipped ? `，另有 ${skipped} 项不适用或尚未验证` : ""}`); }, "专业评测失败")}>运行专业评测</button>
          <button disabled={busy} onClick={() => run(async () => setStorageReport(await getProjectStorage(projectId)), "读取存储用量失败")}>查看项目存储用量</button>
        </div>
        {latestRun && <div className="evaluation-summary">
          <span><b>{latestRun.metrics.professionalScore ?? "—"}</b>专业分</span>
          <span><b>{latestRun.metrics.fixedCasesPassed ?? 0}/{latestRun.metrics.fixedCasesTotal ?? 5}</b>固定测试</span>
          {!!excluded && <span><b>{excluded}</b>项未计入（不适用/未验证）</span>}
          <span><b>{latestRun.metrics.editsPerSlide ?? 0}</b>每页修改</span>
          <span><b>{Math.round((latestRun.metrics.userSelectionRate ?? 0) * 100)}%</b>选择率</span>
          {latestRun.metrics.blindReady && <a href={blindEvaluationUrl(latestRun.blindToken)} target="_blank" rel="noreferrer">打开双盲评审包</a>}
          {!latestRun.metrics.blindReady && latestRun.metrics.blindReadinessReason && <small>{latestRun.metrics.blindReadinessReason}</small>}
        </div>}
        {storageReport && <div className="evaluation-summary">
          <span><b>{formatBytes(storageReport.totalBytes)}</b>项目文件（{storageReport.totalFiles} 个）</span>
          <span><b>{formatBytes(storageReport.groups.exports.bytes + storageReport.groups.evaluations.bytes)}</b>导出与评测快照</span>
          <span><b>{formatBytes(storageReport.freeBytes)}</b>磁盘可用空间</span>
          {storageReport.freeBytes < 1024 ** 3 && <small>磁盘空间不足 1 GB，建议先备份并清理不再需要的文件。</small>}
          {storageReport.backupIncludesAllArtifacts && <small>工作区备份会包含这些项目文件。</small>}
        </div>}
      </div>
    </details>
  );
}
