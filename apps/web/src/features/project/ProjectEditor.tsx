import { PersonalLearningPanel } from "./PersonalLearningPanel";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  addProjectMember,
  approveOutline,
  approveSample,
  bindLicensedAsset,
  blindEvaluationUrl,
  cancelProjectJob,
  candidatePreviewUrl,
  chatEditSlide,
  editImportedPowerPointObject,
  generateNarration,
  getProfessionalPlatform,
  getProjectWorkspace,
  getSlideChat,
  getSlideVersions,
  importedPowerPointExportUrl,
  importPowerPoint,
  publishProject,
  recordProjectApproval,
  registerLicensedAsset,
  renameProject,
  repairSlide,
  rollbackSlide,
  runProfessionalEvaluation,
  runVisualRegression,
  selectSlideCandidate,
  setPowerPointEffects,
  singleSlideExportUrl,
  startGenerateJob,
  startFullGenerationJob,
  startSampleJob,
  startSlideRegenerateJob,
  updateProjectSkills,
  updateSlideLayout,
  uploadBrandAsset,
  validateProject,
  waitForProjectJob,
} from "../../api";
import type { ProjectJob, QualityReport, Skill } from "../../api";
import { Empty } from "../../components/Empty";
import { JobPageProgress } from "../../components/JobPageProgress";
import { ProfessionalPlatformPanel } from "../../components/ProfessionalPlatformPanel";
import { skillDescription, skillName } from "../skills/skillMeta";
import { ProjectPreview } from "./ProjectPreview";
import { SlideRail } from "./SlideRail";
import { SourceUnderstanding } from "./SourceUnderstanding";
import { VARIANT_LABELS } from "./presentationMeta";

export function ProjectEditor({
  projectId,
  skills,
  back,
  refreshProjects,
}: {
  projectId: string;
  skills: Skill[];
  back: () => void;
  refreshProjects: () => void;
}) {
  const workspace = useQuery({
      queryKey: ["project-workspace", projectId],
      queryFn: () => getProjectWorkspace(projectId),
    }),
    data = workspace.data,
    [slideId, setSlideId] = useState(""),
    [title, setTitle] = useState(""),
    [message, setMessage] = useState(""),
    [bullets, setBullets] = useState(""),
    [projectName, setProjectName] = useState(""),
    [selectedSkills, setSelectedSkills] = useState<string[]>([]),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false),
    [activeJob, setActiveJob] = useState<ProjectJob | null>(null),
    [previewKey, setPreviewKey] = useState(0),
    [qualityReport, setQualityReport] = useState<QualityReport | null>(null),
    [editTarget, setEditTarget] = useState("title"),
    [editValue, setEditValue] = useState(""),
    [assetFile, setAssetFile] = useState<File | null>(null),
    [assetName, setAssetName] = useState(""),
    [assetLicense, setAssetLicense] = useState("owned"),
    [assetAttribution, setAssetAttribution] = useState(""),
    [brandFile, setBrandFile] = useState<File | null>(null),
    [memberName, setMemberName] = useState(""),
    [pptTransition, setPptTransition] = useState("fade"),
    [pptAnimation, setPptAnimation] = useState("none"),
    [importedSlideIndex, setImportedSlideIndex] = useState(1),
    [importedObjectId, setImportedObjectId] = useState(""),
    [importedObjectValue, setImportedObjectValue] = useState("");
  const professional = useQuery({
    queryKey: ["professional-platform", projectId, previewKey],
    queryFn: () => getProfessionalPlatform(projectId),
  });
  const current = data?.slides.find((slide) => slide.id === slideId) ?? data?.slides[0];
  const currentCandidates = (data?.candidates ?? []).filter((candidate) => candidate.slideId === current?.id);
  const importedSlide = data?.importedPowerPoint?.analysis.slides.find((slide) => slide.position === importedSlideIndex);
  const importedEditableObjects = (importedSlide?.objects || []).filter((item) => item.editable);
  const versions = useQuery({
    queryKey: ["slide-versions", projectId, current?.id],
    queryFn: () => getSlideVersions(projectId, current!.id),
    enabled: Boolean(current?.id),
  });
  const chatHistory = useQuery({
    queryKey: ["slide-chat", projectId, current?.id],
    queryFn: () => getSlideChat(projectId, current!.id),
    enabled: Boolean(current?.id),
  });
  useEffect(() => {
    if (data && !slideId && data.slides[0]) setSlideId(data.slides[0].id);
    if (data) {
      setProjectName(data.project.name);
      setSelectedSkills(data.skillIds);
    }
  }, [data, slideId]);
  useEffect(() => {
    if (!current) return;
    setTitle(current.content.title ?? "");
    setMessage(current.message ?? "");
    setBullets((current.content.bullets ?? []).join("\n"));
  }, [current?.id, current?.content.title, current?.message]);
  useEffect(() => {
    const selected = importedEditableObjects.find((item) => item.id === importedObjectId) || importedEditableObjects[0];
    if (selected) {
      setImportedObjectId(selected.id);
      setImportedObjectValue(selected.text);
    } else {
      setImportedObjectId("");
      setImportedObjectValue("");
    }
  }, [importedSlideIndex, data?.importedPowerPoint?.version]);
  useEffect(() => {
    if (!data?.previewAvailable) return;
    validateProject(projectId).then(setQualityReport).catch(() => setQualityReport(null));
  }, [data?.previewAvailable, projectId, previewKey]);
  const showJobProgress = (prefix: string) => (job: ProjectJob) => {
    const percent = Math.max(1, Math.round(job.progress * 100));
    setActiveJob(job);
    setStatus(`${prefix} · ${job.checkpoint.label || "正在处理"}（${percent}%）`);
  };
  async function monitorJob(initial: ProjectJob, prefix: string) {
    setActiveJob(initial);
    try {
      return await waitForProjectJob(initial, showJobProgress(prefix));
    } finally {
      setActiveJob(null);
    }
  }

  async function saveSlide() {
    if (!current) return;
    setBusy(true);
    setStatus("正在保存本页修改…");
    try {
      await repairSlide(projectId, current.id, "用户在项目工作区微调", {
        message: message.trim() || title.trim(),
        content: {
          ...current.content,
          title: title.trim(),
          bullets: bullets.split("\n").map((x) => x.trim()).filter(Boolean),
        },
      }, current.revision);
      await workspace.refetch();
      await versions.refetch();
      setStatus("修改已保存，并创建了可回退的新版本");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function sendObjectEdit() {
    if (!current || !editValue.trim()) return;
    const bulletMatch = editTarget.match(/^bullet-(\d+)$/);
    const target = bulletMatch ? { kind: "bullet", index: Number(bulletMatch[1]) } : { kind: editTarget };
    setBusy(true);
    setStatus("正在只修改指定对象并重新渲染当前页…");
    try {
      await chatEditSlide(projectId, current.id, `修改${editTarget}`, target, "replace", editValue.trim(), current.revision);
      setEditValue("");
      await Promise.all([workspace.refetch(), versions.refetch(), chatHistory.refetch()]);
      setPreviewKey((value) => value + 1);
      setStatus("对象级修改已完成，其他页面保持不变");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "对象修改失败");
    } finally { setBusy(false); }
  }
  async function regenerateCurrentSlide() {
    if (!current) return;
    setBusy(true);
    setStatus("正在单独重新生成当前页…");
    try {
      await monitorJob(await startSlideRegenerateJob(projectId, current.id), "单页生成");
      await workspace.refetch();
      setPreviewKey((value) => value + 1);
      setStatus("当前页已重新生成，其他页面和选择保持不变");
    } catch (error) { setStatus(error instanceof Error ? error.message : "单页生成失败"); }
    finally { setBusy(false); }
  }
  async function rebuild() {
    setBusy(true);
    setStatus("正在根据最新内容重新生成全部页面…");
    try {
      const pendingApproval = Boolean(
        data?.gates?.enabled &&
        (data.gates.outline !== "approved" || data.gates.sample !== "approved"),
      );
      const job = await monitorJob(
        pendingApproval
          ? await startFullGenerationJob(
              projectId,
              data?.planOptions.title || projectName,
              data?.planOptions.instructions || "",
              data?.planOptions.preset || "academic",
              data?.planOptions.slideCount || data?.slides.length || 12,
              data?.skillIds || [],
              data?.planOptions.imageMode === "auto" ? "auto" : "off",
              data?.planOptions.professionalBrief || {},
            )
          : await startGenerateJob(projectId),
        "重新生成",
      );
      const generated = job.checkpoint.result as { slides?: number; readySlides?: number; failedPages?: { position: number }[] } | undefined;
      await workspace.refetch();
      setPreviewKey((value) => value + 1);
      if (generated?.failedPages?.length) {
        setQualityReport(null);
        setStatus(`已完成 ${generated.readySlides || 0}/${generated.slides || 0} 页；第 ${generated.failedPages.map((page) => page.position).join("、")} 页失败，可单独重试`);
        return;
      }
      const quality = await validateProject(projectId);
      setQualityReport(quality);
      setStatus(
        `已重新生成 ${generated?.slides || data?.slides.length || 0} 页，质量检查${quality.passed ? "通过" : "需要复核"}`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "重新生成失败");
    } finally {
      setBusy(false);
    }
  }
  async function confirmOutlineAndBuildSample() {
    setBusy(true);
    setStatus("正在确认大纲并生成封面、中间页和结尾页样张…");
    try {
      await approveOutline(projectId);
      await monitorJob(
        await startSampleJob(projectId),
        "生成代表样张",
      );
      await workspace.refetch();
      setPreviewKey((value) => value + 1);
      setStatus("代表样张已生成，请检查排版与风格后再确认");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "样张生成失败");
    } finally {
      setBusy(false);
    }
  }
  async function confirmSampleAndBuildDeck() {
    setBusy(true);
    setStatus("样张已确认，正在批量生成并执行事实与视觉质量检查…");
    try {
      await approveSample(projectId);
      const job = await monitorJob(
        await startGenerateJob(projectId),
        "生成完整演示",
      );
      const generated = job.checkpoint.result as { slides?: number; readySlides?: number; failedPages?: { position: number }[] } | undefined;
      await workspace.refetch();
      setPreviewKey((value) => value + 1);
      if (generated?.failedPages?.length) {
        setQualityReport(null);
        setStatus(`已完成 ${generated.readySlides || 0}/${generated.slides || 0} 页；第 ${generated.failedPages.map((page) => page.position).join("、")} 页失败，可进入对应页面单独重试`);
        return;
      }
      const quality = await validateProject(projectId);
      setQualityReport(quality);
      setStatus(`已生成 ${generated?.slides || data?.slides.length || 0} 页，综合质量检查${quality.passed ? "通过" : "需要复核"}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "完整生成失败");
    } finally {
      setBusy(false);
    }
  }
  async function applySkillsAndReplan() {
    setBusy(true);
    setStatus("正在应用视觉方案，并通过内置流程重新生成…");
    try {
      await updateProjectSkills(projectId, selectedSkills);
      const job = await monitorJob(
        await startFullGenerationJob(
          projectId,
          data?.planOptions.title || projectName,
          data?.planOptions.instructions || "",
          data?.planOptions.preset || "academic",
          data?.planOptions.slideCount || data?.slides.length || 12,
          selectedSkills,
          data?.planOptions.imageMode === "auto" ? "auto" : "off",
          data?.planOptions.professionalBrief || {},
        ),
        "应用视觉方案",
      );
      const generated = job.checkpoint.result as { slides?: number; readySlides?: number; failedPages?: { position: number }[] } | undefined;
      setSlideId("");
      await workspace.refetch();
      setPreviewKey((value) => value + 1);
      if (generated?.failedPages?.length) {
        setQualityReport(null);
        setStatus(`视觉方案已应用到 ${generated.readySlides || 0}/${generated.slides || 0} 页；第 ${generated.failedPages.map((page) => page.position).join("、")} 页可单独重试`);
        return;
      }
      const quality = await validateProject(projectId);
      setQualityReport(quality);
      setStatus(
        `视觉方案已应用并重新生成 ${generated?.slides || data?.slides.length || 0} 页，质量检查${quality.passed ? "通过" : "需要复核"}`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "视觉方案应用失败");
    } finally {
      setBusy(false);
    }
  }
  if (workspace.isLoading) return <Empty title="正在打开项目" text="正在读取页面、来源和版本记录…" />;
  if (!data) return <Empty title="项目打开失败" text="请返回项目列表后重试。" />;
  return (
    <section className="content project-workspace">
      <div className="workspace-toolbar">
        <button className="back-button" onClick={back}>← 返回项目库</button>
        <div className="project-name-editor">
          <input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
          <button
            onClick={async () => {
              await renameProject(projectId, projectName);
              refreshProjects();
              setStatus("项目名称已保存");
            }}
          >保存名称</button>
        </div>
        <span className="count">{data.slides.length} 页 · {data.sources.length} 份材料</span>
      </div>
      <div className={`generation-command${busy ? " is-busy" : ""}`} aria-live="polite">
        <div className="generation-command__mark">{busy ? <span className="spinner" /> : "✦"}</div>
        <div className="generation-command__copy">
          <span>当前工作流 · 第 {String(current?.position ?? 1).padStart(2, "0")} 页</span>
          <b>{status || "修改内容后保存当前页，或重新生成全稿并自动完成质量检查"}</b>
        </div>
        {activeJob && !activeJob.checkpoint.cancelRequested && (
          <button className="generation-command__cancel" onClick={async () => {
            const job = await cancelProjectJob(activeJob.id);
            setActiveJob(job);
            setStatus(job.checkpoint.label || "已请求取消任务");
          }}>取消任务</button>
        )}
        <div className="generation-command__actions">
          <button disabled={busy || !title.trim()} onClick={saveSlide}>保存当前页</button>
          <button className="primary" disabled={busy} onClick={rebuild}>
            {busy ? "正在处理…" : "重新生成全稿"}
          </button>
        </div>
        {activeJob && <div className="generation-command__progress"><JobPageProgress job={activeJob} /></div>}
      </div>
      {data.gates?.enabled && (data.gates.outline !== "approved" || data.gates.sample !== "approved") && (
        <div className="approval-gate">
          <div><b>生成确认</b><p>先审阅左侧页面大纲，再检查 3 页代表样张；确认后才批量生成，避免整套返工。</p></div>
          <span className={data.gates.outline === "approved" ? "done" : "active"}>1 大纲</span>
          <span className={data.gates.sample === "approved" ? "done" : data.gates.outline === "approved" ? "active" : ""}>2 样张</span>
          {data.gates.outline !== "approved" ? (
            <button disabled={busy} onClick={confirmOutlineAndBuildSample}>确认大纲并生成样张</button>
          ) : !data.sampleAvailable ? (
            <button disabled={busy} onClick={confirmOutlineAndBuildSample}>生成／重试代表样张</button>
          ) : (
            <button disabled={busy || !data.sampleAvailable} onClick={confirmSampleAndBuildDeck}>确认样张并生成全稿</button>
          )}
        </div>
      )}
      {data.personalization?.active && <div className="panel"><b>本次采用的个人经验</b><p>{data.personalization.rules.map(rule => `${rule.label}：${rule.description}`).join("；") || "当前档案暂无已确认规则"}</p><small>仅应用符合场景和质量约束的规则；个人样式会与普通样式实际渲染对照。</small></div>}
      {data.personalizationAvailable && <PersonalLearningPanel projectId={projectId} />}
      <SourceUnderstanding sources={data.sources} />
      {data.slides.some(slide => slide.imageGeneration?.status === "deferred") && <div className="panel"><b>部分配图待完成，页面仍可继续生成</b><p>本轮使用原文素材或原生排版保留全部正文。重新生成可继续查询已提交的配图任务。</p><ul>{data.slides.filter(slide => slide.imageGeneration?.status === "deferred").map(slide => <li key={slide.id}>第 {slide.position} 页：{slide.imageGeneration?.message}</li>)}</ul></div>}
      <div className="editor-layout">
        <SlideRail slides={data.slides} currentId={current?.id} onSelect={setSlideId} />
        <div className="editor-main">
          <div className="panel slide-editor">
            <div className="panel-title">
              <span className="number">{String(current?.position ?? 1).padStart(2, "0")}</span>
              <div><h3>微调当前页面</h3><p>标题、核心结论和要点均可修改</p></div>
            </div>
            <label>页面标题<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
            <label>核心结论<textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
            <label>页面要点<textarea rows={6} value={bullets} onChange={(e) => setBullets(e.target.value)} placeholder="每行一个要点" /></label>
            {currentCandidates.length > 0 && (
              <div className="candidate-picker">
                <div className="candidate-heading">
                  <div><b>选择本页版式</b><small>选择会同步到 HTML、PDF 与可编辑 PPTX</small></div>
                  <span>{currentCandidates.length} 个候选</span>
                </div>
                <div className="candidate-grid">
                  {currentCandidates.map((candidate) => (
                    <button
                      type="button"
                      key={candidate.id}
                      className={candidate.selected ? "selected" : ""}
                      disabled={busy || !candidate.previewAvailable}
                      onClick={async () => {
                        if (!current || candidate.selected) return;
                        setBusy(true);
                        setStatus(`正在应用“${VARIANT_LABELS[candidate.variant] || candidate.variant}”版式…`);
                        try {
                          await selectSlideCandidate(projectId, current.id, candidate.id, current.revision);
                          await workspace.refetch();
                          setPreviewKey((value) => value + 1);
                          setStatus("候选版式已应用到全部导出格式");
                        } catch (error) {
                          setStatus(error instanceof Error ? error.message : "候选版式应用失败");
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {candidate.previewAvailable ? (
                        <img
                          src={`${candidatePreviewUrl(projectId, candidate.slideId, candidate.id)}?v=${previewKey}`}
                          alt={`${VARIANT_LABELS[candidate.variant] || candidate.variant} 候选预览`}
                        />
                      ) : <span className="candidate-missing">预览待生成</span>}
                      <span className="candidate-meta">
                        <b>{VARIANT_LABELS[candidate.variant] || candidate.variant}</b>
                        <small>
                          {candidate.score.overall ?? "—"} 分
                          {candidate.score.contentFit != null ? ` · 内容匹配 ${candidate.score.contentFit}` : ""}
                        </small>
                      </span>
                      {candidate.selected && <i>已选</i>}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <ProfessionalPlatformPanel
            data={professional.data}
            slide={current}
            loading={professional.isLoading}
            busy={busy}
            onVisualRegression={async (acceptCurrent) => {
              setBusy(true);
              try {
                const result = await runVisualRegression(projectId, acceptCurrent);
                setStatus(result.status === "baseline-created" ? "视觉基线已保存" : result.passed ? "视觉变化检查通过" : "检测到需要复核的视觉变化");
              } catch (error) {
                setStatus(error instanceof Error ? error.message : "视觉变化检查失败");
              } finally {
                setBusy(false);
              }
            }}
            onSaveLayout={async (regions, focalPoint) => {
              if (!current) return;
              setBusy(true);
              try {
                await updateSlideLayout(projectId, current.id, regions, focalPoint, current.revision);
                await Promise.all([workspace.refetch(), versions.refetch(), professional.refetch()]);
                setStatus("页面画布布局已保存为新版本；重新生成后会进入 HTML 与 PPTX");
              } catch (error) {
                setStatus(error instanceof Error ? error.message : "画布布局保存失败");
              } finally {
                setBusy(false);
              }
            }}
          />
          <details className="panel p1-studio">
            <summary><span><b>页内对话与对象编辑</b><small>只改标题、结论、单条要点或视觉类型</small></span><i>P1</i></summary>
            <div className="object-edit-grid">
              <select value={editTarget} onChange={(event) => setEditTarget(event.target.value)}>
                <option value="title">页面标题</option>
                <option value="message">核心结论</option>
                {(current?.content.bullets || []).map((_, index) => <option key={index} value={`bullet-${index}`}>第 {index + 1} 条要点</option>)}
                <option value="visual">主视觉类型</option>
              </select>
              {editTarget === "visual" ? (
                <select value={editValue} onChange={(event) => setEditValue(event.target.value)}>
                  <option value="">选择视觉类型</option><option value="chart">图表</option><option value="table">表格</option><option value="diagram">关系图</option><option value="typography">文字叙事</option>
                </select>
              ) : <input value={editValue} onChange={(event) => setEditValue(event.target.value)} placeholder="输入替换后的内容" />}
              <button className="primary" disabled={busy || !editValue.trim()} onClick={sendObjectEdit}>应用到指定对象</button>
            </div>
            <div className="partial-actions">
              <button disabled={busy} onClick={regenerateCurrentSlide}>只重新生成当前页</button>
              {current && <a href={singleSlideExportUrl(projectId, current.id)}>导出当前页 PPTX</a>}
            </div>
            {(chatHistory.data || []).length > 0 && <div className="chat-history">
              {(chatHistory.data || []).slice(-3).map((item) => <p key={item.id}><b>{item.actor}</b><span>{item.instruction}</span><small>版本 {item.version}</small></p>)}
            </div>}
          </details>
          <details className="panel p1-studio">
            <summary><span><b>品牌、素材与协作</b><small>授权台账、品牌资产、成员审批和安全发布</small></span><i>展开</i></summary>
            <div className="p1-section">
              <b>合规素材</b>
              <input value={assetName} onChange={(event) => setAssetName(event.target.value)} placeholder="素材名称" />
              <div className="p1-row">
                <select value={assetLicense} onChange={(event) => setAssetLicense(event.target.value)}><option value="owned">自有版权</option><option value="internal">内部授权</option><option value="cc0">CC0</option><option value="cc-by">CC BY</option><option value="unsplash">Unsplash</option></select>
                <input value={assetAttribution} onChange={(event) => setAssetAttribution(event.target.value)} placeholder="作者 / 归属信息" />
              </div>
              <input type="file" accept=".png,.jpg,.jpeg,.webp,.svg,.mp4,.webm,.mov,.mp3,.wav,.m4a" onChange={(event) => setAssetFile(event.currentTarget.files?.[0] || null)} />
              <button disabled={busy || !assetName.trim() || !assetFile} onClick={async () => {
                const kind = assetFile?.type.startsWith("video/") ? "video" : assetFile?.type.startsWith("audio/") ? "audio" : "image";
                setBusy(true); try { await registerLicensedAsset(projectId, { name: assetName, kind, provider: "uploaded", sourceUrl: "", license: assetLicense, attribution: assetAttribution, file: assetFile }); await workspace.refetch(); await professional.refetch(); setAssetName(""); setAssetFile(null); setStatus(`${kind === "video" ? "视频" : kind === "audio" ? "音频" : "图片"}素材已登记授权台账`); } catch (error) { setStatus(error instanceof Error ? error.message : "素材登记失败"); } finally { setBusy(false); }
              }}>登记合规素材</button>
              {(data.licensedAssets || []).map((asset) => <div className="asset-ledger-row" key={asset.id}><span><b>{asset.name}</b><small>{asset.license} · {asset.attribution || "自有"}</small></span>{current && asset.approved && <button onClick={async () => { await bindLicensedAsset(projectId, current.id, asset.id); await workspace.refetch(); setStatus("合规素材已绑定到当前页"); }}>用于当前页</button>}</div>)}
            </div>
            <div className="p1-section">
              <b>品牌资产</b>
              <input type="file" accept=".png,.jpg,.jpeg,.svg" onChange={(event) => setBrandFile(event.currentTarget.files?.[0] || null)} />
              <button disabled={busy || !brandFile} onClick={async () => { if (!brandFile) return; setBusy(true); try { await uploadBrandAsset(projectId, brandFile.name, "logo", brandFile); await workspace.refetch(); setBrandFile(null); setStatus("品牌标识已加入项目资产库"); } catch (error) { setStatus(error instanceof Error ? error.message : "品牌资产上传失败"); } finally { setBusy(false); } }}>上传品牌标识</button>
            </div>
            <div className="p1-section">
              <b>成员与审批</b>
              <div className="p1-row"><input value={memberName} onChange={(event) => setMemberName(event.target.value)} placeholder="成员姓名" /><button disabled={!memberName.trim()} onClick={async () => { await addProjectMember(projectId, memberName, "reviewer"); setMemberName(""); await workspace.refetch(); }}>添加审阅人</button></div>
              <div className="member-list">{(data.members || []).map((member) => <span key={member.id}>{member.name} · {member.role}</span>)}</div>
              <div className="approval-actions"><button onClick={async () => { await recordProjectApproval(projectId, "final", "changes_requested", "需要继续修改"); await workspace.refetch(); setStatus("已记录修改意见"); }}>要求修改</button><button className="primary" onClick={async () => { await recordProjectApproval(projectId, "final", "approved", "同意发布"); await workspace.refetch(); setStatus("最终审批已通过"); }}>批准发布</button><button onClick={async () => { try { const result = await publishProject(projectId); await workspace.refetch(); await navigator.clipboard?.writeText(`${location.origin}${result.url}`); setStatus("安全发布链接已创建并复制"); } catch (error) { setStatus(error instanceof Error ? error.message : "发布失败"); } }}>创建发布链接</button></div>
              {(data.publications || []).filter((item) => item.status === "active").map((item) => <a className="publication-link" key={item.id} href={`/api/v1/public/decks/${item.token}`} target="_blank" rel="noreferrer">打开发布快照</a>)}
            </div>
          </details>
          <details className="panel p2-studio">
            <summary><span><b>PowerPoint 深度工作台</b><small>转场动画、旁白、现有 PPTX 续编与双盲评测</small></span><i>P2</i></summary>
            <div className="p2-block">
              <b>当前页演示效果</b>
              <div className="p2-controls">
                <select value={pptTransition} onChange={(event) => setPptTransition(event.target.value)}>
                  <option value="none">无转场</option><option value="fade">淡化</option><option value="push">推进</option><option value="wipe">擦除</option>
                </select>
                <select value={pptAnimation} onChange={(event) => setPptAnimation(event.target.value)}>
                  <option value="none">无对象动画</option><option value="fade">主对象淡入</option>
                </select>
                <button disabled={busy || !current} onClick={async () => {
                  if (!current) return; setBusy(true);
                  try { await setPowerPointEffects(projectId, current.id, pptTransition, pptAnimation); await Promise.all([workspace.refetch(), versions.refetch()]); setStatus("当前页转场与动画已写入 PowerPoint 规格"); }
                  catch (error) { setStatus(error instanceof Error ? error.message : "演示效果保存失败"); }
                  finally { setBusy(false); }
                }}>保存效果</button>
              </div>
              <div className="partial-actions">
                <button disabled={busy || !current} onClick={async () => { if (!current) return; setBusy(true); try { const result = await generateNarration(projectId, current.id); await Promise.all([workspace.refetch(), versions.refetch()]); setStatus(`已生成当前页旁白，预计 ${result.totalSeconds} 秒`); } catch (error) { setStatus(error instanceof Error ? error.message : "旁白生成失败"); } finally { setBusy(false); } }}>生成当前页旁白</button>
                <button disabled={busy} onClick={async () => { setBusy(true); try { const result = await generateNarration(projectId); await workspace.refetch(); setStatus(`已生成全稿旁白，预计 ${Math.ceil(result.totalSeconds / 60)} 分钟`); } catch (error) { setStatus(error instanceof Error ? error.message : "全稿旁白生成失败"); } finally { setBusy(false); } }}>生成全稿旁白</button>
              </div>
            </div>
            <div className="p2-block">
              <b>导入现有 PPTX 继续编辑</b>
              <label className="p2-upload"><input type="file" accept=".pptx" disabled={busy} onChange={async (event) => { const file = event.currentTarget.files?.[0]; if (!file) return; setBusy(true); setStatus("正在读取现有 PPTX 的母版、动画和对象…"); try { await importPowerPoint(projectId, file); setImportedSlideIndex(1); setImportedObjectId(""); await workspace.refetch(); setStatus("PPTX 已导入，可按对象继续编辑"); } catch (error) { setStatus(error instanceof Error ? error.message : "PPTX 导入失败"); } finally { setBusy(false); event.currentTarget.value = ""; } }} /><span>选择 PPTX</span></label>
              {data.importedPowerPoint && <>
                <div className="fidelity-strip">
                  <span>{data.importedPowerPoint.analysis.slideCount} 页</span><span>{data.importedPowerPoint.analysis.masterCount} 个母版</span><span>{data.importedPowerPoint.analysis.layoutCount} 个版式</span><span>{data.importedPowerPoint.analysis.animationSlides} 页动画</span><span>{data.importedPowerPoint.analysis.transitionSlides} 页转场</span>
                </div>
                <div className="p2-object-editor">
                  <select value={importedSlideIndex} onChange={(event) => setImportedSlideIndex(Number(event.target.value))}>{data.importedPowerPoint.analysis.slides.map((slide) => <option key={slide.position} value={slide.position}>第 {slide.position} 页 · {slide.title || "未命名"}</option>)}</select>
                  <select value={importedObjectId} onChange={(event) => { const id = event.target.value; setImportedObjectId(id); setImportedObjectValue(importedEditableObjects.find((item) => item.id === id)?.text || ""); }}>{importedEditableObjects.map((item) => <option key={item.id} value={item.id}>{item.name || `对象 ${item.id}`}</option>)}</select>
                  <textarea rows={3} value={importedObjectValue} onChange={(event) => setImportedObjectValue(event.target.value)} placeholder="选择可编辑文字对象" />
                  <button className="primary" disabled={busy || !importedObjectId} onClick={async () => { setBusy(true); try { await editImportedPowerPointObject(projectId, importedSlideIndex, importedObjectId, importedObjectValue); await workspace.refetch(); setStatus("对象文字已更新，主题、母版、动画和转场保持不变"); } catch (error) { setStatus(error instanceof Error ? error.message : "对象修改失败"); } finally { setBusy(false); } }}>保存对象修改</button>
                </div>
                <a className="publication-link" href={importedPowerPointExportUrl(projectId)}>导出高忠实往返 PPTX</a>
              </>}
            </div>
            <div className="p2-block">
              <b>固定测试集与双盲评审</b>
              <button disabled={busy} onClick={async () => { setBusy(true); try { const result = await runProfessionalEvaluation(projectId); await workspace.refetch(); setStatus(`专业评测已完成：固定测试 ${result.metrics.fixedCasesPassed}/${result.metrics.fixedCasesTotal}`); } catch (error) { setStatus(error instanceof Error ? error.message : "专业评测失败"); } finally { setBusy(false); } }}>运行专业评测</button>
              {data.evaluationRuns?.[0] && <div className="evaluation-summary">
                <span><b>{data.evaluationRuns[0].metrics.professionalScore ?? "—"}</b>专业分</span>
                <span><b>{data.evaluationRuns[0].metrics.fixedCasesPassed ?? 0}/{data.evaluationRuns[0].metrics.fixedCasesTotal ?? 5}</b>固定测试</span>
                <span><b>{data.evaluationRuns[0].metrics.editsPerSlide ?? 0}</b>每页修改</span>
                <span><b>{Math.round((data.evaluationRuns[0].metrics.userSelectionRate ?? 0) * 100)}%</b>选择率</span>
                {data.evaluationRuns[0].metrics.blindReady && <a href={blindEvaluationUrl(data.evaluationRuns[0].blindToken)} target="_blank" rel="noreferrer">打开双盲评审包</a>}
              </div>}
            </div>
          </details>
          <div className="panel project-settings">
            <div className="panel-title">
              <span className="number purple">✦</span>
              <div><h3>视觉排版方案</h3><p>只改变设计表达；解析、规划与质检始终内置</p></div>
            </div>
            <div className="skill-options compact-options">
              <label className="skill-option">
                <input
                  type="radio"
                  name="project-visual-skill"
                  checked={!selectedSkills.length}
                  onChange={() => setSelectedSkills([])}
                />
                <span><b>映章默认视觉系统</b><small>现代、克制、适合大多数中文演示。</small></span>
              </label>
              {skills.map((skill) => (
                <label className="skill-option" key={skill.id}>
                  <input
                    type="radio"
                    name="project-visual-skill"
                    checked={selectedSkills.includes(skill.id)}
                    onChange={() => setSelectedSkills([skill.id])}
                  />
                  <span><b>{skillName(skill)}</b><small>{skillDescription(skill)}</small></span>
                </label>
              ))}
            </div>
            <div className="settings-actions">
              <button
                className="secondary-wide"
                onClick={async () => {
                  await updateProjectSkills(projectId, selectedSkills);
                  await workspace.refetch();
                  setStatus("项目技能选择已保存");
                }}
              >保存视觉方案</button>
              <button className="primary" disabled={busy} onClick={applySkillsAndReplan}>
                应用方案并重新生成
              </button>
            </div>
          </div>
          {!!data.modelPlanning?.filledByBuiltinPlanner && <div className="panel" role="alert">
            <strong>部分页面仍需检查内容</strong>
            <p>模型未完成 {data.modelPlanning.filledByBuiltinPlanner} 页的规划，这些页面暂用原文整理的底稿。请检查标题、重点与叙事衔接，也可以更换模型后重新规划。</p>
            {!!data.modelPlanning.batchErrors?.length && <details><summary>查看原因</summary><p>{data.modelPlanning.batchErrors[0]}</p></details>}
          </div>}
          <details className="panel orchestration-panel compact-contract">
            <summary>
              <span><b>查看本项目的生成方法</b><small>{data.orchestration?.policy?.label || "纯规则规划"} · {data.orchestration?.batches?.length || 0} 个分段</small></span>
              <i>展开</i>
            </summary>
            <p>{data.orchestration?.principle || "系统守住事实和交付底线，小模型分段完成策略与页面表达"}</p>
            <div className="ownership-grid">
              <div><b>系统守住</b><p>{(data.orchestration?.ruleOwned || []).slice(0, 5).join("、") || "页数、证据、数字与质量检查"}</p></div>
              <div><b>模型参与</b><p>{(data.orchestration?.modelOwned || []).join("、") || "策略、页面责任、标题和视觉提案"}</p></div>
            </div>
          </details>
          <div className="panel version-panel">
            <div className="panel-title"><span className="number">↺</span><div><h3>版本记录</h3><p>任何微调都可以回退</p></div></div>
            <div className="version-list">
              {(versions.data ?? []).slice().reverse().map((version) => (
                <div key={version.version}>
                  <span>版本 {version.version}</span><small>{version.reason}</small>
                  <button
                    disabled={busy || version.version === (versions.data?.at(-1)?.version ?? 0)}
                    onClick={async () => {
                      if (!current) return;
                      await rollbackSlide(projectId, current.id, version.version);
                      await workspace.refetch();
                      await versions.refetch();
                      setStatus(`已回退到版本 ${version.version}`);
                    }}
                  >恢复</button>
                </div>
              ))}
            </div>
          </div>
        </div>
        <ProjectPreview
          projectId={projectId}
          data={data}
          previewKey={previewKey}
          busy={busy}
          qualityReport={qualityReport}
          setBusy={setBusy}
          setStatus={setStatus}
        />
      </div>
    </section>
  );
}
