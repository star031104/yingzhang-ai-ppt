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
import { CreatePage } from "./features/create/CreatePage";
import { ModelsPage } from "./features/models/ModelsPage";
import { ProjectEditor } from "./features/project/ProjectEditor";
import { SkillsPage } from "./features/skills/SkillsPage";
import type { ProfessionalBrief, PublicSession } from "./api";
import { PersonalizationPage, getPersonalProfiles } from "./features/personalization/PersonalizationPage";
import "./style.css";

type View = "create" | "projects" | "project" | "models" | "skills" | "personalization";
const NAV: { id: View; label: string; icon: string }[] = [
  { id: "create", label: "新建演示", icon: "＋" },
  { id: "projects", label: "我的项目", icon: "▦" },
  { id: "models", label: "模型配置", icon: "◇" },
  { id: "personalization", label: "我的助手", icon: "◎" },
  { id: "skills", label: "技能库", icon: "✦" },
];
function readRoute(): { view: View; projectId: string } {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash.startsWith("project/")) {
    return { view: "project", projectId: hash.slice("project/".length) };
  }
  const view = (["create", "projects", "models", "skills", "personalization"] as View[]).includes(hash as View)
    ? (hash as View)
    : "create";
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
        setToast(`已解析 ${files.length} 份材料，正在合并证据与识别材料分工…`);
      } else {
        setToast("正在根据主题与要求建立创作简报…");
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
      setToast(`已自动生成 ${result?.readySlides || result?.slides || Number(data.get("slides"))} 页，正在打开结果…`);
      qc.invalidateQueries({ queryKey: ["projects"] });
      setActiveProjectId(project.id);
      navigate("project", project.id);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "生成失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app-shell">
      <aside>
        <div className="brand">
          <div className="brand-mark">映</div>
          <div>
            <strong>映章</strong>
            <small>智能演示创作</small>
          </div>
        </div>
        <nav>
          {NAV.filter((item) => (isAdmin || item.id !== "models") && (!session.publicMode || item.id !== "personalization")).map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "active" : ""}
              onClick={() => navigate(item.id)}
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="aside-tip">
          <b>从证据到表达</b>
          <p>来源可追溯，页面可编辑，风格可复用。</p>
        </div>
        {session.publicMode && (
          <div className="aside-account">
            <div><span>{(session.name || "访").slice(0, 1)}</span><p><b>{session.name || "访问者"}</b><small>{isAdmin ? "管理员" : "协作测试者"}</small></p></div>
            <button onClick={onLogout}>退出登录</button>
          </div>
        )}
      </aside>
      <main>
        <header>
          <div>
            <p className="breadcrumb">
              映章工作台 / {view === "project" ? "项目编辑" : NAV.find((x) => x.id === view)?.label}
            </p>
            <h1>
              {view === "create"
                ? "开始一场有章法的演示"
                : view === "projects"
                  ? "项目与成果"
                  : view === "models"
                    ? "模型连接与分工"
                    : view === "personalization"
                      ? "我的助手与个人经验"
                    : view === "skills"
                      ? "技能扩展中心"
                      : "项目编辑工作区"}
            </h1>
          </div>
          <div className="session-tools">
            <div className="system-status">
              <i></i>{session.publicMode || session.privateMode
                ? `${session.name || "访问者"} · ${isAdmin ? "管理员" : "协作测试者"}`
                : "本地工作区"}
            </div>
            {(session.publicMode || session.privateMode) && <button className="logout-button" onClick={onLogout}>退出登录</button>}
          </div>
        </header>
        {view === "create" && (
          <CreatePage
            build={build}
            busy={busy}
            toast={toast}
            projectId={projectId}
            skills={skills.data ?? []}
            personalProfiles={session.publicMode ? [] : personalProfiles.data?.profiles ?? []}
          />
        )}{" "}
        {view === "projects" && (
          <ProjectsPage
            projects={projects.data ?? []}
            openProject={(id) => {
              navigate("project", id);
            }}
            refresh={() => qc.invalidateQueries({ queryKey: ["projects"] })}
            canDelete={isAdmin}
          />
        )}{" "}
        {view === "project" && activeProjectId && (
          <ProjectEditor
            projectId={activeProjectId}
            skills={skills.data ?? []}
            back={() => navigate("projects")}
            refreshProjects={() => qc.invalidateQueries({ queryKey: ["projects"] })}
          />
        )}{" "}
        {isAdmin && view === "models" && (
          <ModelsPage
            providers={providers.data ?? []}
            models={models.data ?? []}
            refresh={() => {
              qc.invalidateQueries({ queryKey: ["providers"] });
              qc.invalidateQueries({ queryKey: ["models"] });
            }}
          />
        )}{" "}
        {!session.publicMode && view === "personalization" && <PersonalizationPage />}
        {session.publicMode && view === "personalization" && <p>私人记忆仅在本机个人工作区开放。</p>}
        {view === "skills" && (
          <SkillsPage
            skills={skills.data ?? []}
            refresh={() => qc.invalidateQueries({ queryKey: ["skills"] })}
            canManage={isAdmin}
          />
        )}
      </main>
    </div>
  );
}

function ProjectsPage({
  projects,
  openProject,
  refresh,
  canDelete,
}: {
  projects: { id: string; name: string; status: string }[];
  openProject: (id: string) => void;
  refresh: () => void;
  canDelete: boolean;
}) {
  return (
    <section className="content">
      <div className="section-heading">
        <div>
          <span className="kicker">项目库</span>
          <h2>最近的演示项目</h2>
        </div>
        <span className="count">{projects.length} 个项目</span>
      </div>
      {projects.length ? (
        <div className="project-grid">
          {projects.map((project, index) => (
            <article
              className="project-card"
              key={project.id}
              tabIndex={0}
              role="button"
              onClick={() => openProject(project.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") openProject(project.id);
              }}
            >
              <div className={`cover cover-${index % 3}`}>
                <span>映章</span>
                <b>{String(index + 1).padStart(2, "0")}</b>
              </div>
              <div>
                <h3>{project.name}</h3>
                <div className={`project-status ${project.status === "ready" ? "ready" : ""}`}><i />{project.status === "ready" ? "已就绪" : project.status}</div>
                <small className="project-id">项目 {project.id.slice(0, 8)}</small>
                <div className="project-actions">
                  <button className="open-project" type="button">
                    打开并继续编辑 →
                  </button>
                  {canDelete && <button
                    className="danger-link"
                    type="button"
                    onClick={async (event) => {
                      event.stopPropagation();
                      if (!window.confirm(`确定删除“${project.name}”吗？项目会移入本地回收目录。`)) return;
                      await removeProject(project.id);
                      refresh();
                    }}
                  >删除</button>}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="还没有项目"
          text="从“新建演示”上传第一份材料，映章会为你保留全部中间产物。"
        />
      )}
    </section>
  );
}
