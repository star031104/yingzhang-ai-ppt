import { useState } from "react";
import type { FormEvent } from "react";

import { exportUrl } from "../../api";
import type { Skill } from "../../api";
import type { PersonalProfile } from "../personalization/PersonalizationPage";
import { Notice } from "../../components/Notice";
import { skillName } from "../skills/skillMeta";

export function CreatePage({
  build,
  busy,
  toast,
  projectId,
  skills,
  personalProfiles = [],
}: {
  build: (e: FormEvent<HTMLFormElement>) => void;
  busy: boolean;
  toast: string;
  projectId: string;
  skills: Skill[];
  personalProfiles?: PersonalProfile[];
}) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [instructions, setInstructions] = useState("");
  const quickPrompts = [
    "根据材料制作本科毕业答辩 PPT，内容详细、重点突出",
    "把这个主题做成专业汇报，结论先行，图表优先",
    "制作一份清晰有说服力的演示，自动判断受众与结构",
  ];
  return (
    <>
      <section className="intro compact-intro">
        <div>
          <span className="kicker">一句话开始</span>
          <h2>
            说清要做什么，<em>其余交给映章</em>
          </h2>
          <p>
            不用写复杂提示词，也不一定上传文件。映章会先理解材料，再让小模型分段规划、创作和复核。
          </p>
        </div>
        <div className="intro-proof">
          <span><b>01</b> 理解材料</span>
          <span><b>02</b> 分段创作</span>
          <span><b>03</b> 全局复核</span>
        </div>
      </section>
      <section className="workspace-grid refined-create-grid">
        <form className="panel create-form" onSubmit={build}>
          <div className="panel-title">
            <span className="number">01</span>
            <div>
              <h3>新建演示</h3>
              <p>一句话足够，细节可以稍后调整</p>
            </div>
          </div>
          {personalProfiles.length > 0 && <label>本次使用的个人经验<select name="personalProfile" defaultValue=""><option value="">本次不使用个人经验</option>{personalProfiles.map(item => <option key={item.id} value={item.id}>{item.name}{item.use_memory ? "" : "（已暂停）"}</option>)}</select><small className="field-help">只使用与演示场景匹配的规则。本次明确要求优先；质量不合格时恢复普通方案。</small></label>}
          <label>
            演示标题
            <input
              name="title"
              required
              placeholder="例如：基于证据图谱的长文档演示生成方法"
            />
          </label>
          <label>
            你希望怎样制作
            <textarea
              name="instructions"
              rows={3}
              value={instructions}
              onChange={(event) => setInstructions(event.currentTarget.value)}
              placeholder="例如：根据材料制作本科毕业答辩 PPT，内容详细一点"
            />
          </label>
          <div className="quick-prompts" aria-label="简短提示词示例">
            <span>一键示例</span>
            {quickPrompts.map((prompt) => (
              <button type="button" key={prompt} onClick={() => setInstructions(prompt)}>{prompt}</button>
            ))}
          </div>
          <label>
            参考材料 <span className="optional-mark">可选</span>
            <div className="file-field">
              <input
                name="sources"
                type="file"
                multiple
                accept=".pdf,.docx,.xlsx,.csv,.pptx,.md,.txt,.html,.png,.jpg,.jpeg"
                onChange={(event) => setSelectedFiles(Array.from(event.currentTarget.files ?? []))}
              />
              <span>可以一次选择多份文件；系统会区分主论文、补充数据、参考演示与图片证据。支持 PDF、Word、Excel、CSV、PPT、Markdown 和图片。</span>
              {selectedFiles.length > 0 && (
                <div className="selected-materials">
                  <b>已选择 {selectedFiles.length} 份材料</b>
                  {selectedFiles.map((file) => (
                    <i key={`${file.name}-${file.size}`}>{file.name}<small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></i>
                  ))}
                </div>
              )}
            </div>
          </label>
          <div className="form-row">
            <label>
              演示类型
              <select name="preset">
                <option value="academic">毕业答辩 / 学术汇报</option>
                <option value="conference">学术会议 / 研究分享</option>
                <option value="business">商业汇报</option>
                <option value="strategy">战略规划 / 咨询建议</option>
                <option value="executive">高管决策简报</option>
                <option value="review">项目复盘 / 经营复盘</option>
                <option value="product">产品发布</option>
                <option value="pitch">融资路演</option>
                <option value="marketing">营销创意提案</option>
                <option value="sales">销售解决方案</option>
                <option value="teaching">课程教学</option>
                <option value="training">企业培训 / 工作坊</option>
                <option value="public">政务 / 公共事务汇报</option>
                <option value="keynote">主题演讲</option>
                <option value="portfolio">作品集 / 案例展示</option>
              </select>
            </label>
            <label>
              页数
              <input name="slides" type="number" min="6" max="60" defaultValue="12" />
            </label>
          </div>
          <details className="advanced-options">
            <summary><span>视觉与高级选项</span><small>默认设置已经适合大多数演示</small></summary>
            <div className="brief-grid">
              <label>目标受众<input name="audience" placeholder="例如：答辩委员会、公司管理层、潜在投资人" /></label>
              <label>预计时长<input name="durationMinutes" type="number" min="3" max="180" placeholder="例如：15 分钟" /></label>
              <label className="wide">希望受众最终理解或决定什么<input name="objective" placeholder="例如：认可方案可行性，并批准进入试点" /></label>
              <label>表达语气
                <select name="tone" defaultValue="auto">
                  <option value="auto">根据内容自动判断</option>
                  <option value="formal">严谨克制</option>
                  <option value="executive">结论先行</option>
                  <option value="editorial">编辑叙事</option>
                  <option value="energetic">鲜明有张力</option>
                </select>
              </label>
              <label>品牌 / 组织 <span className="optional-mark">可选</span><input name="brandName" placeholder="用于封面与页眉，不再显示工具品牌" /></label>
            </div>
            <fieldset className="skill-picker visual-picker">
              <legend>视觉排版方案 <span>可选，单选</span></legend>
              <select name="skills" defaultValue="">
                <option value="">映章默认视觉系统</option>
                {skills.map((skill) => <option key={skill.id} value={skill.id}>{skillName(skill)}</option>)}
              </select>
              <small className="field-help">这里只改变版式风格；解析、规划、事实检查始终内置。</small>
            </fieldset>
            <label className="check image-option">
              <input type="checkbox" name="imageMode" value="auto" />
              <span>
                <b>为封面生成具体主题配图</b>
                <small>只生成与主题直接相关的真实场景或科学画面；数据、架构和实验页仍使用可编辑图表或原文图。</small>
              </span>
            </label>
          </details>
          <div className="builtin-note"><b>内置专业流程</b><span>材料解析 · 策略记忆 · 三页一组创作 · 一致性复核 · 事实与视觉质检</span></div>
          <button className="primary" disabled={busy}>
            {busy ? <><span className="spinner"></span>正在生成…</> : "开始智能生成 →"}
          </button>
        </form>
        <div className="panel flow-panel">
          <div className="panel-title">
            <span className="number purple">02</span>
            <div>
              <h3>映章会怎样完成</h3>
              <p>小模型分段思考，系统负责守住事实底线</p>
            </div>
          </div>
          {[
            ["理解", "识别材料分工，建立章节、数字、图表和来源索引"],
            ["规划", "先形成全局策略记忆，再给每三页分配递进任务"],
            ["创作", "逐段写标题、结论和要点，并提出可验证的视觉方案"],
            ["复核", "检查重复、错位、密度和数字来源，再导出可编辑成果"],
          ].map(([name, text], index) => (
            <div className="flow-phase" key={name}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div><b>{name}</b><p>{text}</p></div>
            </div>
          ))}
          <blockquote>“根据材料制作本科毕业答辩 PPT，内容详细一点”这样的短提示词，就应该得到完整结果。</blockquote>
          {toast && <Notice text={toast} tone={toast.includes("完成") ? "success" : "info"} />} {" "}
          {projectId && (
            <div className="export-bar">
              <p>导出成果</p>
              <a href={exportUrl(projectId, "html")}>HTML</a>
              <a href={exportUrl(projectId, "pptx")}>PPTX</a>
              <a href={exportUrl(projectId, "pdf")}>PDF</a>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
