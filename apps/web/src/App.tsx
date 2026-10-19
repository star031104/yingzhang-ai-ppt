import { FormEvent, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProject,
  getModels,
  getProjects,
  getProviders,
  getSkills,
  removeProject,
  startFullGenerationJob,
  uploadSource,
  waitForProjectJob,
} from "./api";
import { Empty } from "./components/Empty";
import { Icon } from "./components/Icon";
import type { IconName } from "./components/Icon";
import { Skeleton } from "./components/Skeleton";
import { Toaster } from "./components/Toaster";
import { CreatePage } from "./features/create/CreatePage";
import { ModelsPage } from "./features/models/ModelsPage";
import { ProjectEditor } from "./features/project/ProjectEditor";
import { SettingsPage } from "./features/settings/SettingsPage";
import { SkillsPage } from "./features/skills/SkillsPage";
import type { Project, ProfessionalBrief, PublicSession } from "./api";
import { PersonalizationPage, getPersonalProfiles } from "./features/personalization/PersonalizationPage";
import { usePreferences, useResolvedTheme } from "./store/preferences";
import "./styles/index.css";

type View = "create" | "projects" | "project" | "models" | "skills" | "personalization" | "settings";
const NAV: { id: View; label: string; icon: IconName }[] = [
  { id: "create", label: "新建演示", icon: "plus" },
  { id: "projects", label: "我的项目", icon: "folder" },
  { id: "models", label: "模型配置", icon: "chip" },
  { id: "personalization", label: "我的助手", icon: "user" },
  { id: "skills", label: "技能库", icon: "sparkles" },
];
const ROUTES: View[] = ["create", "projects", "models", "skills", "personalization", "settings"];
function readRoute(): { view: View; projectId: string } {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash.startsWith("project/")) {
    return { view: "project", projectId: hash.slice("project/".length) };
  }
  const view = ROUTES.includes(hash as View) ? (hash as View) : "create";
  return { view, projectId: "" };
}
export function App({
  session,
  onLogout,
}: {
  session: PublicSession;
  onLogout: () => void;
}) {
  const initialRoute = useMemo(() => readRoute(), []);
  const isAdmin = session.role === "admin";
  const qc = useQueryClient(),
    [view, setView] = useState<View>(
      !isAdmin && initialRoute.view === "models" ? "create" : initialRoute.view,
    ),
    [toast, setToast] = useState(""),
    [busy, setBusy] = useState(false),
    [projectId, setProjectId] = useState(""),
    [activeProjectId, setActiveProjectId] = useState(initialRoute.projectId);
  const { sidebarCollapsed, toggleSidebar, setTheme } = usePreferences();
  const resolvedTheme = useResolvedTheme();
  const projects = useQuery({ queryKey: ["projects"], queryFn: getProjects }),
    providers = useQuery({ queryKey: ["providers"], queryFn: getProviders, enabled: isAdmin }),
    models = useQuery({ queryKey: ["models"], queryFn: getModels, enabled: isAdmin }),
    skills = useQuery({ queryKey: ["skills"], queryFn: getSkills });
  const personalProfiles = useQuery({ queryKey: ["personal-profiles"], queryFn: getPersonalProfiles, enabled: !session.publicMode });
  useEffect(() => {
    const handleRoute = () => {
      const route = readRoute();
      setView(!isAdmin && route.view === "models" ? "create" : route.view);
      if (route.projectId) setActiveProjectId(route.projectId);
    };
    window.addEventListener("hashchange", handleRoute);
    return () => window.removeEventListener("hashchange", handleRoute);
  }, [isAdmin]);
  function navigate(nextView: View, id = "") {
    setView(nextView);
    if (id) setActiveProjectId(id);
    window.location.hash = nextView === "project" ? `project/${id}` : nextView;
  }
  async function build(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget),
      files = data.getAll("sources").filter((item): item is File => item instanceof File && item.size > 0);
    setBusy(true);
    try {
      setToast("正在创建项目…");
      const project = await createProject(String(data.get("title")));
      setProjectId(project.id);
      if (files.length) {
        for (const [index, file] of files.entries()) {
          setToast(`正在解析第 ${index + 1}/${files.length} 份材料：${file.name}`);
          await uploadSource(project.id, file);
        }
        setToast(`已解析 ${files.length} 份材料，正在整合证据并识别各材料的用途…`);
      } else {
        setToast("正在根据主题与要求整理创作简报…");
      }
      setToast("正在自动规划并生成完整演示…");
      const completed = await waitForProjectJob(
        await startFullGenerationJob(
          project.id,
          String(data.get("title")),
          String(data.get("instructions")),
          String(data.get("preset")),
          Number(data.get("slides")),
          data.getAll("skills").map(String).filter(Boolean),
          data.get("imageMode") === "auto" ? "auto" : "off",
          {
            profileId: String(data.get("personalProfile") || ""),
            profileRevision: personalProfiles.data?.profiles.find(item => item.id === data.get("personalProfile"))?.revision,
            audience: String(data.get("audience") || ""),
            objective: String(data.get("objective") || ""),
            brandName: String(data.get("brandName") || ""),
            tone: String(data.get("tone") || "auto") as ProfessionalBrief["tone"],
            durationMinutes: Number(data.get("durationMinutes")) || null,
          },
        ),
        (job) => {
          const percent = Math.max(1, Math.round(job.progress * 100));
          setToast(`${job.checkpoint.label || "后台正在生成"}（${percent}%）`);
        },
      );
      const result = completed.checkpoint.result as { slides?: number; readySlides?: number } | undefined;
      setToast(`已完成 ${result?.readySlides || result?.slides || Number(data.get("slides"))} 页，正在打开结果…`);
      qc.invalidateQueries({ queryKey: ["projects"] });
      setActiveProjectId(project.id);
      navigate("project", project.id);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "生成失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }
  const navItems = NAV.filter((item) => (isAdmin || item.id !== "models") && (!session.publicMode || item.id !== "personalization"));
  const currentProject = projects.data?.find((project) => project.id === activeProjectId);
  const crumbs = view === "project"
    ? ["我的项目", currentProject?.name || "项目编辑"]
    : [view === "settings" ? "偏好设置" : NAV.find((x) => x.id === view)?.label || ""];
  const accountLabel = session.publicMode || session.privateMode
    ? `${session.name || "访问者"} · ${isAdmin ? "管理员" : "协作测试者"}`
    : "本地工作区";
  return (
    <div className={`app-shell${sidebarCollapsed ? " is-collapsed" : ""}${view === "project" ? " is-project" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">映</div>
          <div className="brand-text">
            <strong>映章</strong>
            <small>智能演示工作台</small>
          </div>
        </div>
        <nav aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id || (item.id === "projects" && view === "project") ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
              title={sidebarCollapsed ? item.label : undefined}
              onClick={() => navigate(item.id)}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <nav aria-label="设置">
            <button
              type="button"
              className={view === "settings" ? "active" : ""}
              aria-current={view === "settings" ? "page" : undefined}
              title={sidebarCollapsed ? "偏好设置" : undefined}
              onClick={() => navigate("settings")}
            >
              <Icon name="sliders" size={18} />
              <span>偏好设置</span>
            </button>
          </nav>
          {session.publicMode && (
            <div className="aside-account">
              <span className="avatar">{(session.name || "访").slice(0, 1)}</span>
              <p><b>{session.name || "访问者"}</b><small>{isAdmin ? "管理员" : "协作测试者"}</small></p>
            </div>
          )}
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button type="button" className="ghost icon-button sidebar-toggle" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"} title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}>
            <Icon name="sidebar" />
          </button>
          <nav className="breadcrumb" aria-label="当前位置">
            <span>映章</span>
            {crumbs.map((crumb, index) => (
              <span key={`${crumb}-${index}`} className={index === crumbs.length - 1 ? "current" : ""}>
                <Icon name="chevronRight" size={12} />
                {index === 0 && view === "project"
                  ? <a href="#projects" onClick={(event) => { event.preventDefault(); navigate("projects"); }}>{crumb}</a>
                  : crumb}
              </span>
            ))}
          </nav>
          <div className="session-tools">
            <div className="system-status" title={accountLabel}><i />{accountLabel}</div>
            <button
              type="button"
              className="ghost icon-button"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
              aria-label={resolvedTheme === "dark" ? "切换到浅色主题" : "切换到深色主题"}
              title={resolvedTheme === "dark" ? "切换到浅色主题" : "切换到深色主题"}
            >
              <Icon name={resolvedTheme === "dark" ? "sun" : "moon"} />
            </button>
            {(session.publicMode || session.privateMode) && (
              <button type="button" className="ghost logout-button" onClick={onLogout}>
                <Icon name="logout" />退出登录
              </button>
            )}
          </div>
        </header>
        <main className={`page page-${view}`}>
          {view === "create" && (
            <CreatePage
              build={build}
              busy={busy}
              toast={toast}
              projectId={projectId}
              skills={skills.data ?? []}
              personalProfiles={session.publicMode ? [] : personalProfiles.data?.profiles ?? []}
            />
          )}
          {view === "projects" && (
            <ProjectsPage
              projects={projects.data ?? []}
              loading={projects.isLoading}
              openProject={(id) => navigate("project", id)}
              createProject={() => navigate("create")}
              refresh={() => qc.invalidateQueries({ queryKey: ["projects"] })}
              canDelete={isAdmin}
            />
          )}
          {view === "project" && activeProjectId && (
            <ProjectEditor
              projectId={activeProjectId}
              skills={skills.data ?? []}
              back={() => navigate("projects")}
              refreshProjects={() => qc.invalidateQueries({ queryKey: ["projects"] })}
            />
          )}
          {isAdmin && view === "models" && (
            <ModelsPage
              providers={providers.data ?? []}
              models={models.data ?? []}
              refresh={() => {
                qc.invalidateQueries({ queryKey: ["providers"] });
                qc.invalidateQueries({ queryKey: ["models"] });
              }}
            />
          )}
          {!session.publicMode && view === "personalization" && <PersonalizationPage />}
          {session.publicMode && view === "personalization" && (
            <Empty icon="lock" title="私人记忆仅在本机开放" text="个人经验只保存在本机个人工作区，协作测试环境不提供此功能。" />
          )}
          {view === "skills" && (
            <SkillsPage
              skills={skills.data ?? []}
              refresh={() => qc.invalidateQueries({ queryKey: ["skills"] })}
              canManage={isAdmin}
            />
          )}
          {view === "settings" && <SettingsPage session={session} />}
        </main>
      </div>
      <Toaster />
    </div>
  );
}

const STATUS_LABELS: Record<string, string> = { ready: "已就绪", draft: "草稿", generating: "生成中", failed: "生成失败" };

function ProjectsPage({
  projects,
  loading,
  openProject,
  createProject,
  refresh,
  canDelete,
}: {
  projects: Pick<Project, "id" | "name" | "status">[];
  loading: boolean;
  openProject: (id: string) => void;
  createProject: () => void;
  refresh: () => void;
  canDelete: boolean;
}) {
  return (
    <section className="content">
      <div className="section-heading">
        <div>
          <span className="kicker">项目库</span>
          <h2>最近的演示项目</h2>
          <p>所有材料、页面版本和导出文件都保存在本机，可以随时回来继续编辑。</p>
        </div>
        <div className="section-actions">
          <span className="count">{projects.length} 个项目</span>
          <button type="button" className="primary" onClick={createProject}><Icon name="plus" />新建演示</button>
        </div>
      </div>
      {loading ? (
        <div className="project-grid" aria-busy="true">
          {Array.from({ length: 6 }, (_, index) => (
            <div className="project-card is-skeleton" key={index}>
              <Skeleton className="cover" height="auto" radius={0} />
              <div className="project-card-body"><Skeleton width="70%" height={14} /><Skeleton width="40%" height={11} /></div>
            </div>
          ))}
        </div>
      ) : projects.length ? (
        <div className="project-grid">
          {projects.map((project, index) => (
            <article
              className="project-card"
              key={project.id}
              tabIndex={0}
              role="button"
              aria-label={`打开项目：${project.name}`}
              onClick={() => openProject(project.id)}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openProject(project.id);
                }
              }}
            >
              <div className={`cover cover-${index % 3}`} aria-hidden="true">
                <span className="cover-lines"><i /><i /><i /></span>
                <b>{String(index + 1).padStart(2, "0")}</b>
              </div>
              <div className="project-card-body">
                <h3>{project.name}</h3>
                <div className="project-meta">
                  <span className={`project-status ${project.status === "ready" ? "ready" : ""}`}><i />{STATUS_LABELS[project.status] || project.status}</span>
                  <small className="project-id">#{project.id.slice(0, 8)}</small>
                </div>
                <div className="project-actions">
                  <button className="open-project ghost btn-sm" type="button" tabIndex={-1}>
                    继续编辑<Icon name="arrowRight" size={14} />
                  </button>
                  {canDelete && <button
                    className="danger-link btn-sm"
                    type="button"
                    onClick={async (event) => {
                      event.stopPropagation();
                      if (!window.confirm(`确定删除“${project.name}”吗？项目会移入本地回收目录。`)) return;
                      await removeProject(project.id);
                      refresh();
                    }}
                  ><Icon name="trash" size={14} />删除</button>}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="panel">
          <Empty
            icon="folder"
            title="还没有项目"
            text="从“新建演示”开始，上传材料或写一句要求。映章会保存全部中间产物，方便随时继续编辑。"
            action={<button type="button" className="primary" onClick={createProject}><Icon name="plus" />新建第一个演示</button>}
          />
        </div>
      )}
    </section>
  );
}
