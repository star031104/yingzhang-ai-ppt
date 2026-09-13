import { useState } from "react";

import { compileReferenceSkill, installSkillUrl, removeSkill } from "../../api";
import type { Skill } from "../../api";
import { Empty } from "../../components/Empty";
import { Notice } from "../../components/Notice";
import { skillDescription, skillName, skillTags } from "./skillMeta";


export function SkillsPage({
  skills,
  refresh,
  canManage,
}: {
  skills: Skill[];
  refresh: () => void;
  canManage: boolean;
}) {
  const [url, setUrl] = useState(""),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false),
    [referenceFile, setReferenceFile] = useState<File | null>(null),
    [referenceName, setReferenceName] = useState("");
  async function install() {
    setBusy(true);
    setStatus("正在下载并进行安全检查…");
    try {
      const skill = await installSkillUrl(url, false);
      setStatus(`技能 ${skill.id} ${skill.version} 安装成功`);
      setUrl("");
      refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "安装失败");
    } finally {
      setBusy(false);
    }
  }
  async function learnReference() {
    if (!referenceFile) return;
    setBusy(true);
    setStatus("正在识别页面功能、版式规律和视觉节奏…");
    try {
      const result = await compileReferenceSkill(referenceFile, referenceName);
      setStatus(`参考稿已学习为技能 ${result.id}`);
      setReferenceFile(null);
      setReferenceName("");
      refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "参考稿学习失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="content">
      <div className="section-heading">
        <div>
          <span className="kicker">技能扩展</span>
          <h2>把好风格，变成可复用能力</h2>
          <p>这里只管理排版、配色、字体层级和图表表达；解析、规划、拆解与质检已经内置。</p>
        </div>
        <span className="count">已安装 {skills.length}</span>
      </div>
      <div className={`skills-layout ${canManage ? "" : "readonly"}`}>
        {canManage && <div className="panel skill-install">
          <div className="panel-title">
            <span className="number">＋</span>
            <div>
              <h3>从项目链接安装</h3>
              <p>支持 GitHub、GitLab 与 ZIP 下载链接</p>
            </div>
          </div>
          <label>
            项目链接
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/组织名/技能项目"
            />
          </label>
          <div className="skill-safety-note"><b>仅安装视觉规则</b><p>社区脚本始终保持禁用；解析、规划和生成流程不会被外部项目替换。</p></div>
          <button className="primary" onClick={install} disabled={!url || busy}>
            {busy ? "正在安装…" : "下载、检查并安装 →"}
          </button>
          <div className="reference-learning">
            <div><b>从优秀 PPT 学习</b><small>学习封面、章节、数据、对比、流程与结论页的功能规律，不复制原文。</small></div>
            <input
              type="text"
              value={referenceName}
              onChange={(event) => setReferenceName(event.target.value)}
              placeholder="技能名称（可选）"
            />
            <label className="reference-file">
              <input
                type="file"
                accept=".pptx"
                disabled={busy}
                onChange={(event) => setReferenceFile(event.currentTarget.files?.[0] || null)}
              />
              <span>{referenceFile ? referenceFile.name : "选择参考 PPTX"}</span>
            </label>
            <button className="secondary" onClick={learnReference} disabled={!referenceFile || busy}>
              {busy && referenceFile ? "正在学习…" : "学习并安装为视觉技能"}
            </button>
          </div>
          {status && (
            <Notice
              text={status}
              tone={
                status.includes("成功")
                  ? "success"
                  : status.includes("失败") || status.includes("detail")
                    ? "error"
                    : "info"
              }
            />
          )}
          <div className="security-row">
            <span>路径校验</span>
            <span>静态扫描</span>
            <span>版本锁定</span>
            <span>哈希记录</span>
          </div>
        </div>}
        <div className="panel skill-list">
          <div className="panel-title">
            <span className="number purple">✦</span>
            <div>
              <h3>已安装技能</h3>
              <p>社区规则已做视觉化适配，默认不执行外部脚本</p>
            </div>
          </div>
          {skills.length ? (
            skills.map((skill) => (
              <article key={skill.id}>
                <div className="skill-icon">技</div>
                <div className="skill-summary">
                  <b>{skillName(skill)}</b>
                  <small>{skillDescription(skill)}</small>
                  <div className="skill-tags">
                    {skillTags(skill).map((tag) => <span key={tag}>{tag}</span>)}
                    <span>版本 {skill.version}</span>
                    <span>{skill.scriptsEnabled ? "脚本已授权" : "安全隔离"}</span>
                  </div>
                </div>
                {canManage && <button
                  onClick={async () => {
                    if (!window.confirm(`确定卸载“${skillName(skill)}”吗？`)) return;
                    await removeSkill(skill.id);
                    refresh();
                  }}
                >
                  卸载
                </button>}
              </article>
            ))
          ) : (
            <Empty
              title="技能库还是空的"
              text="安装一个视觉、品牌或布局技能，让映章学会你喜欢的表达方式。"
            />
          )}
        </div>
      </div>
    </section>
  );
}
