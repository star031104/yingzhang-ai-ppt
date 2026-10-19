import { PersonalLearningPanel } from "./PersonalLearningPanel";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  approveOutline,
  approveSample,
  cancelProjectJob,
  chatEditSlide,
  getProfessionalPlatform,
  getProjectWorkspace,
  getSlideChat,
  getSlideVersions,
  renameProject,
  repairSlide,
  runVisualRegression,
  selectSlideCandidate,
  singleSlideExportUrl,
  startGenerateJob,
  startFullGenerationJob,
  startSampleJob,
  startSlideRegenerateJob,
  updateProjectSkills,
  updateSlideLayout,
  validateProject,
  waitForProjectJob,
} from "../../api";
import type { ProjectJob, QualityReport, RegionEditResult, Skill, SlideCandidate } from "../../api";
import { Empty } from "../../components/Empty";
import { Icon } from "../../components/Icon";
import { JobPageProgress } from "../../components/JobPageProgress";
import { ProfessionalPlatformPanel } from "../../components/ProfessionalPlatformPanel";
import { Skeleton, SkeletonLines } from "../../components/Skeleton";
import { usePreferences } from "../../store/preferences";
import { toast } from "../../store/toasts";
import { skillDescription, skillName } from "../skills/skillMeta";
import { BrandAssetsPanel } from "./BrandAssetsPanel";
import { CandidatePicker } from "./CandidatePicker";
import { CollaborationPanel } from "./CollaborationPanel";
import { PowerPointWorkbench } from "./PowerPointWorkbench";
import { ProjectPreview } from "./ProjectPreview";
import { QualityCenter } from "./QualityCenter";
import { ProposalReviewPanel, SlideProposalNote } from "./ProposalReview";
import { SlideRail } from "./SlideRail";
import { SourceUnderstanding } from "./SourceUnderstanding";
import { VersionPanel } from "./VersionPanel";
import { WorkflowStepper, workflowStates } from "./WorkflowStepper";
import type { WorkflowStep } from "./WorkflowStepper";
import { VARIANT_LABELS } from "./presentationMeta";

type InspectorTab = "edit" | "layout" | "quality" | "history";
const TABS: { id: InspectorTab; label: string }[] = [
  { id: "edit", label: "内容" },
  { id: "layout", label: "版式" },
  { id: "quality", label: "质量" },
  { id: "history", label: "版本" },
];

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
    [tab, setTab] = useState<InspectorTab>("edit"),
    [regionToolRequest, setRegionToolRequest] = useState(0);
  const advanced = usePreferences((state) => state.advanced);
  const sourcesRef = useRef<HTMLDivElement>(null);
  const professional = useQuery({
    queryKey: ["professional-platform", projectId, previewKey],
    queryFn: () => getProfessionalPlatform(projectId),
    enabled: advanced,
  });
  const current = data?.slides.find((slide) => slide.id === slideId) ?? data?.slides[0];
  const currentCandidates = (data?.candidates ?? []).filter((candidate) => candidate.slideId === current?.id);
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
  }, [current?.id, current?.content.title, current?.message, current?.revision]);
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
  const refreshSlide = () => Promise.all([workspace.refetch(), versions.refetch(), chatHistory.refetch()]);

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
      toast("本页修改已保存", "success");
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
      await refreshSlide();
      setPreviewKey((value) => value + 1);
      setStatus("对象级修改已完成，其他页面保持不变");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "对象修改失败");
    } finally { setBusy(false); }
  }
  async function onRegionEdited(result: RegionEditResult) {
    await refreshSlide();
    setPreviewKey((value) => value + 1);
    const labels = result.edited.map((item) => item.label).join("、");
    setStatus(`框选修改已完成：${labels}；已保存为版本 ${result.version}`);
    toast(`已修改${labels}`, "success");
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
  async function finishGeneration(job: ProjectJob, verb: string) {
    const generated = job.checkpoint.result as { slides?: number; readySlides?: number; failedPages?: { position: number }[] } | undefined;
    await workspace.refetch();
    setPreviewKey((value) => value + 1);
    if (generated?.failedPages?.length) {
      setQualityReport(null);
      setStatus(`已完成 ${generated.readySlides || 0}/${generated.slides || 0} 页；第 ${generated.failedPages.map((page) => page.position).join("、")} 页失败，可选中该页单独重试`);
      return;
    }
    const quality = await validateProject(projectId);
    setQualityReport(quality);
    setStatus(`${verb} ${generated?.slides || data?.slides.length || 0} 页，质量检查${quality.passed ? "通过" : "需要复核"}`);
  }
  const fullJob = (skillIds: string[]) => startFullGenerationJob(
    projectId,
    data?.planOptions.title || projectName,
    data?.planOptions.instructions || "",
    data?.planOptions.preset || "academic",
    data?.planOptions.slideCount || data?.slides.length || 12,
    skillIds,
    data?.planOptions.imageMode === "auto" ? "auto" : "off",
    data?.planOptions.professionalBrief || {},
  );
  async function rebuild() {
    setBusy(true);
    setStatus("正在根据最新内容重新生成全部页面…");
    try {
      const pendingApproval = Boolean(
        data?.gates?.enabled &&
        (data.gates.outline !== "approved" || data.gates.sample !== "approved"),
      );
      const needsPlanning = !data?.slides.length;
      const job = await monitorJob(
        pendingApproval || needsPlanning || data?.retryFullGeneration
          ? await fullJob(data?.skillIds || [])
          : await startGenerateJob(projectId),
        "重新生成",
      );
      await finishGeneration(job, "已重新生成");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "重新生成失败");
    } finally {
      setBusy(false);
    }
  }
  async function confirmOutlineAndBuildSample() {
    setBusy(true);
    setStatus("正在确认大纲，并生成封面、中间页和结尾页样张…");
    try {
      await approveOutline(projectId);
      await monitorJob(await startSampleJob(projectId), "生成代表样张");
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
    setStatus("样张已确认，正在批量生成并检查事实与视觉质量…");
    try {
      await approveSample(projectId);
      const job = await monitorJob(await startGenerateJob(projectId), "生成完整演示");
      await finishGeneration(job, "已生成");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "完整生成失败");
    } finally {
      setBusy(false);
    }
  }
  async function applySkillsAndReplan() {
    setBusy(true);
    setStatus("正在应用视觉方案并重新生成…");
    try {
      await updateProjectSkills(projectId, selectedSkills);
      const job = await monitorJob(await fullJob(selectedSkills), "应用视觉方案");
      setSlideId("");
      await finishGeneration(job, "视觉方案已应用，重新生成");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "视觉方案应用失败");
    } finally {
      setBusy(false);
    }
  }
  async function selectCandidate(candidate: SlideCandidate) {
    if (!current) return;
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
  }
  function goToStep(step: WorkflowStep) {
    if (step === "sources" || (step === "outline" && !data?.slides.length)) {
      sourcesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      sourcesRef.current?.querySelector("details")?.setAttribute("open", "");
    } else if (step === "outline") {
      document.querySelector<HTMLElement>(".slide-rail [aria-current='true']")?.focus();
    } else if (step === "generate") {
      // Never start a long job from navigation; point at the explicit action instead.
      document.querySelector<HTMLElement>(".toolbar-actions .primary")?.focus();
    } else if (step === "edit") {
      setTab("edit");
    } else if (step === "quality") {
      setTab("quality");
    } else if (step === "export") {
      document.getElementById("project-export")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  if (workspace.isLoading) return <WorkspaceSkeleton />;
  if (!data) return <Empty icon="alert" title="项目打开失败" text="请返回项目列表后重试。" action={<button type="button" onClick={back}><Icon name="arrowLeft" />返回项目库</button>} />;
  const steps = workflowStates(data, qualityReport, busy);
  const nameDirty = projectName.trim() !== data.project.name && projectName.trim().length > 0;
  const gatePending = data.gates?.enabled && (data.gates.outline !== "approved" || data.gates.sample !== "approved");
  const contentDirty = Boolean(current) && (
    title !== (current?.content.title ?? "") ||
    message !== (current?.message ?? "") ||
    bullets !== (current?.content.bullets ?? []).join("\n")
  );
  const qualityIssues = qualityReport && !qualityReport.passed;
  return (
    <section className="content project-workspace">
      <div className="workspace-toolbar">
        <button className="ghost icon-button back-button" onClick={back} aria-label="返回项目库" title="返回项目库"><Icon name="arrowLeft" /></button>
        <form
          className="project-name-editor"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!nameDirty) return;
            await renameProject(projectId, projectName.trim());
            refreshProjects();
            await workspace.refetch();
            setStatus("项目名称已保存");
            toast("项目名称已保存", "success");
          }}
        >
          <input value={projectName} onChange={(e) => setProjectName(e.target.value)} aria-label="项目名称" />
          {nameDirty && <button className="btn-sm">保存名称</button>}
        </form>
        <span className="count">{data.slides.length} 页 · {data.sources.length} 份材料</span>
        <WorkflowStepper states={steps} onStep={goToStep} />
        <div className="toolbar-actions">
          <button className="primary" disabled={busy} onClick={rebuild}>
            {busy ? <><span className="spinner" />正在处理…</> : <><Icon name="refresh" size={15} />{data.retryFullGeneration || !data.slides.length
              ? data.sources.length ? "从已上传材料重试生成" : "重试生成演示"
              : "重新生成全稿"}</>}
          </button>
        </div>
      </div>
      {(busy || status || activeJob) && (
        <div className={`generation-command${busy ? " is-busy" : ""}`} aria-live="polite">
          <div className="generation-command__mark">{busy ? <span className="spinner" /> : <Icon name="info" size={15} />}</div>
          <div className="generation-command__copy">
            <span>第 {String(current?.position ?? 1).padStart(2, "0")} 页</span>
            <b>{status || "正在处理…"}</b>
          </div>
          {activeJob && !activeJob.checkpoint.cancelRequested && (
            <button className="generation-command__cancel btn-sm" onClick={async () => {
              const job = await cancelProjectJob(activeJob.id);
              setActiveJob(job);
              setStatus(job.checkpoint.label || "已请求取消任务");
            }}>取消任务</button>
          )}
          {!busy && <button className="ghost icon-button btn-sm" aria-label="关闭状态" onClick={() => setStatus("")}><Icon name="x" size={14} /></button>}
          {activeJob && <div className="generation-command__progress"><JobPageProgress job={activeJob} /></div>}
        </div>
      )}
      {gatePending && (
        <div className="approval-gate">
          <div><b>生成前确认</b><p>先审阅左侧页面大纲，再检查 3 页代表样张；确认后才批量生成，避免整套返工。</p></div>
          <span className={data.gates!.outline === "approved" ? "done" : "active"}>1 大纲</span>
          <span className={data.gates!.sample === "approved" ? "done" : data.gates!.outline === "approved" ? "active" : ""}>2 样张</span>
          {data.gates!.outline !== "approved" ? (
            <button className="primary" disabled={busy} onClick={confirmOutlineAndBuildSample}>确认大纲并生成样张</button>
          ) : !data.sampleAvailable ? (
            <button className="primary" disabled={busy} onClick={confirmOutlineAndBuildSample}>生成 / 重试代表样张</button>
          ) : (
            <button className="primary" disabled={busy || !data.sampleAvailable} onClick={confirmSampleAndBuildDeck}>确认样张并生成全稿</button>
          )}
        </div>
      )}
      <div className="editor-layout">
        <SlideRail slides={data.slides} currentId={current?.id} onSelect={setSlideId} projectId={projectId} candidates={data.candidates} previewKey={previewKey} />
        <ProjectPreview
          projectId={projectId}
          data={data}
          previewKey={previewKey}
          busy={busy}
          setBusy={setBusy}
          setStatus={setStatus}
          currentSlideId={current?.id}
          onRegionEdited={onRegionEdited}
          regionToolRequest={regionToolRequest}
        />
        <aside className="inspector panel" aria-label="页面属性">
          <div className="inspector-head">
            <span className="inspector-number">{String(current?.position ?? 1).padStart(2, "0")}</span>
            <div><b>{current?.content.title || "未选择页面"}</b><small>{current ? `版本 ${current.revision}` : "从左侧选择页面"}</small></div>
          </div>
          <div className="tab-list" role="tablist" aria-label="页面属性分组">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                id={`inspector-tab-${item.id}`}
                aria-selected={tab === item.id}
                aria-controls={`inspector-panel-${item.id}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {item.id === "quality" && qualityIssues && <span className="tab-dot" aria-label="有待处理问题" />}
              </button>
            ))}
          </div>
          <div className="inspector-body" role="tabpanel" id={`inspector-panel-${tab}`} aria-labelledby={`inspector-tab-${tab}`}>
            {tab === "edit" && (
              <div className="slide-editor">
                <SlideProposalNote slide={current} />
                {data.previewAvailable && (
                  <button type="button" className="region-callout" onClick={() => setRegionToolRequest((value) => value + 1)}>
                    <span><Icon name="select" size={16} /></span>
                    <div><b>框选修改</b><small>在预览上框出区域，用一句话说明怎么改</small></div>
                    <Icon name="chevronRight" size={14} />
                  </button>
                )}
                <label>页面标题<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
                <label>核心结论<textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} /></label>
                <label>页面要点<textarea rows={6} value={bullets} onChange={(e) => setBullets(e.target.value)} placeholder="每行一个要点" /></label>
                <div className="editor-actions">
                  {contentDirty && <span className="badge warning">未保存</span>}
                  <button className={contentDirty ? "primary" : ""} disabled={busy || !title.trim()} onClick={saveSlide}>保存当前页</button>
                </div>
                <div className="inspector-section">
                  <div className="inspector-section-head"><div><b>精确修改</b><small>只改一个对象，其余内容保持不变</small></div></div>
                  <div className="object-edit-grid">
                    <select value={editTarget} onChange={(event) => setEditTarget(event.target.value)} aria-label="修改对象">
                      <option value="title">页面标题</option>
                      <option value="message">核心结论</option>
                      {(current?.content.bullets || []).map((_, index) => <option key={index} value={`bullet-${index}`}>第 {index + 1} 条要点</option>)}
                      <option value="visual">主视觉类型</option>
                    </select>
                    {editTarget === "visual" ? (
                      <select value={editValue} onChange={(event) => setEditValue(event.target.value)} aria-label="视觉类型">
                        <option value="">选择视觉类型</option><option value="chart">图表</option><option value="table">表格</option><option value="diagram">关系图</option><option value="typography">文字叙事</option>
                      </select>
                    ) : <input value={editValue} onChange={(event) => setEditValue(event.target.value)} placeholder="输入替换后的内容" aria-label="替换内容" />}
                    <button className="primary" disabled={busy || !editValue.trim()} onClick={sendObjectEdit}>应用</button>
                  </div>
                </div>
                <div className="partial-actions">
                  <button disabled={busy} onClick={regenerateCurrentSlide}><Icon name="refresh" size={14} />只重新生成当前页</button>
                  {current && <a className="button ghost" href={singleSlideExportUrl(projectId, current.id)}><Icon name="download" size={14} />导出当前页</a>}
                </div>
              </div>
            )}
            {tab === "layout" && (
              <div className="layout-tab">
                <CandidatePicker projectId={projectId} candidates={currentCandidates} previewKey={previewKey} busy={busy} onSelect={selectCandidate} />
                <div className="inspector-section project-settings">
                  <div className="inspector-section-head"><div><b>全稿视觉方案</b><small>只改变设计表达；解析、规划与质检始终内置</small></div></div>
                  <div className="skill-options compact-options">
                    <label className="skill-option">
                      <input type="radio" name="project-visual-skill" checked={!selectedSkills.length} onChange={() => setSelectedSkills([])} />
                      <span><b>映章默认视觉系统</b><small>现代、克制，适合大多数中文演示。</small></span>
                    </label>
                    {skills.map((skill) => (
                      <label className="skill-option" key={skill.id}>
                        <input type="radio" name="project-visual-skill" checked={selectedSkills.includes(skill.id)} onChange={() => setSelectedSkills([skill.id])} />
                        <span><b>{skillName(skill)}</b><small>{skillDescription(skill)}</small></span>
                      </label>
                    ))}
                  </div>
                  <div className="settings-actions">
                    <button className="secondary-wide" onClick={async () => { await updateProjectSkills(projectId, selectedSkills); await workspace.refetch(); setStatus("视觉方案已保存"); }}>仅保存</button>
                    <button className="primary" disabled={busy} onClick={applySkillsAndReplan}>应用并重新生成</button>
                  </div>
                </div>
              </div>
            )}
            {tab === "quality" && (
              qualityReport
                ? <QualityCenter report={qualityReport} projectId={projectId} slides={data.slides} onJumpToSlide={setSlideId} />
                : <Empty icon="shield" title={data.previewAvailable ? "正在检查质量…" : "生成后自动检查"} text="内容完整性、事实来源、可读性、对比度与素材许可会在页面生成后自动检查。" />
            )}
            {tab === "history" && (
              <VersionPanel
                projectId={projectId}
                current={current}
                versions={versions.data ?? []}
                chat={chatHistory.data ?? []}
                busy={busy}
                setBusy={setBusy}
                setStatus={setStatus}
                refresh={() => Promise.all([workspace.refetch(), versions.refetch()])}
              />
            )}
          </div>
        </aside>
      </div>
      <div className="workspace-sections" ref={sourcesRef}>
        {!!data.modelPlanning?.filledByBuiltinPlanner && <div className="panel callout warning" role="alert">
          <Icon name="alert" size={16} />
          <div>
            <strong>部分页面仍需检查内容</strong>
            <p>模型未完成 {data.modelPlanning.filledByBuiltinPlanner} 页的规划，这些页面暂用原文整理的底稿。请检查标题、重点与叙事衔接，也可以更换模型后重新规划。</p>
            {!!data.modelPlanning.batchErrors?.length && <details><summary>查看原因</summary><p>{data.modelPlanning.batchErrors[0]}</p></details>}
          </div>
        </div>}
        {data.slides.some(slide => slide.imageGeneration?.status === "deferred") && <div className="panel callout info">
          <Icon name="image" size={16} />
          <div>
            <b>部分配图尚未完成，页面仍可继续生成</b>
            <p>本轮使用原文素材或原生排版保留全部正文。重新生成时会继续查询已提交的配图任务。</p>
            <ul>{data.slides.filter(slide => slide.imageGeneration?.status === "deferred").map(slide => <li key={slide.id}>第 {slide.position} 页：{slide.imageGeneration?.message}</li>)}</ul>
          </div>
        </div>}
        {data.personalization?.active && <div className="panel callout accent">
          <Icon name="user" size={16} />
          <div>
            <b>本次采用的个人经验</b>
            <p>{data.personalization.rules.map(rule => `${rule.label}：${rule.description}`).join("；") || "当前档案暂无已确认的规则"}</p>
            <small>只应用符合场景和质量要求的规则；个人风格会与普通风格实际渲染对照。</small>
          </div>
        </div>}
        <ProposalReviewPanel data={data} onJump={(id) => { setSlideId(id); setTab("edit"); }} />
        <SourceUnderstanding sources={data.sources} documents={data.materialAnalysis?.documents} />
        <BrandAssetsPanel projectId={projectId} data={data} current={current} busy={busy} setBusy={setBusy} setStatus={setStatus} refresh={() => workspace.refetch()} />
        {advanced ? (
          <>
            <div className="sections-divider"><span>高级功能</span></div>
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
                  setStatus("页面画布布局已保存为新版本；重新生成后会应用到 HTML 与 PPTX");
                } catch (error) {
                  setStatus(error instanceof Error ? error.message : "画布布局保存失败");
                } finally {
                  setBusy(false);
                }
              }}
            />
            <CollaborationPanel projectId={projectId} data={data} setStatus={setStatus} refresh={() => workspace.refetch()} />
            <PowerPointWorkbench projectId={projectId} data={data} current={current} busy={busy} setBusy={setBusy} setStatus={setStatus} refresh={() => Promise.all([workspace.refetch(), versions.refetch()])} />
            {data.personalizationAvailable && <PersonalLearningPanel projectId={projectId} />}
            <details className="panel orchestration-panel compact-contract">
              <summary>
                <span><b>本项目的生成方法</b><small>{data.orchestration?.policy?.label || "纯规则规划"} · {data.orchestration?.batches?.length || 0} 个分段</small></span>
              </summary>
              <p>{data.orchestration?.principle || "系统守住事实和交付底线，模型分段完成策略与页面表达"}</p>
              <div className="ownership-grid">
                <div><b>系统负责</b><p>{(data.orchestration?.ruleOwned || []).slice(0, 5).join("、") || "页数、证据、数字与质量检查"}</p></div>
                <div><b>模型参与</b><p>{(data.orchestration?.modelOwned || []).join("、") || "策略、页面任务、标题和视觉提案"}</p></div>
              </div>
            </details>
          </>
        ) : (
          <p className="advanced-hint"><Icon name="lock" size={14} />协作审批、发布、PowerPoint 深度工作台等高级功能已隐藏，可在 <a href="#settings">偏好设置</a> 中开启。</p>
        )}
      </div>
    </section>
  );
}

function WorkspaceSkeleton() {
  return (
    <section className="content project-workspace" aria-busy="true" aria-label="正在打开项目">
      <div className="workspace-toolbar"><Skeleton width={32} height={32} /><Skeleton width={260} height={20} /><Skeleton width={360} height={20} /></div>
      <div className="editor-layout">
        <div className="slide-rail">{Array.from({ length: 5 }, (_, index) => <Skeleton key={index} height={92} />)}</div>
        <div className="preview-column"><Skeleton height={34} width={220} /><div className="preview-stage"><Skeleton className="stage-skeleton" /></div></div>
        <div className="inspector panel"><SkeletonLines lines={6} /></div>
      </div>
    </section>
  );
}
