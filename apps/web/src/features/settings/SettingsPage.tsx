import type { PublicSession } from "../../api";
import { Icon } from "../../components/Icon";
import type { IconName } from "../../components/Icon";
import { AccountPanel } from "../personalization/AccountPanel";
import { usePreferences } from "../../store/preferences";
import type { ThemePreference } from "../../store/preferences";
import { toast } from "../../store/toasts";

const THEMES: { id: ThemePreference; label: string; icon: IconName }[] = [
  { id: "system", label: "跟随系统", icon: "monitor" },
  { id: "light", label: "浅色", icon: "sun" },
  { id: "dark", label: "深色", icon: "moon" },
];

const ADVANCED_FEATURES = [
  "成员、审阅角色与最终审批",
  "安全发布链接与发布快照",
  "专业制作控制台：视觉基线、页面画布、交付兼容性",
  "PowerPoint 深度工作台：转场、旁白、导入现有 PPTX、专业评测",
  "个人经验回传、A/B 对照与办公软件验收",
  "生成方法说明与独立账号管理",
];

export const SIMPLE_WORKFLOW = ["新建", "材料", "大纲", "生成", "编辑", "质量", "导出"];

export function SettingsPage({ session }: { session: PublicSession }) {
  const { theme, setTheme, advanced, setAdvanced } = usePreferences();
  return (
    <section className="content settings-page">
      <div className="section-heading">
        <div>
          <span className="kicker">偏好设置</span>
          <h2>按你的习惯使用映章</h2>
          <p>外观与功能开关只保存在当前浏览器，不影响项目数据和其他成员。</p>
        </div>
      </div>
      <div className="settings-grid">
        <div className="panel settings-card">
          <div className="settings-row">
            <div>
              <h3>外观</h3>
              <p>深色主题适合长时间排版；跟随系统时会随操作系统自动切换。</p>
            </div>
            <div className="theme-options" role="radiogroup" aria-label="界面主题">
              {THEMES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={theme === item.id}
                  className={`theme-option theme-${item.id}${theme === item.id ? " active" : ""}`}
                  onClick={() => setTheme(item.id)}
                >
                  <span className="theme-swatch" aria-hidden="true"><i /><i /><i /></span>
                  <span><Icon name={item.icon} size={14} />{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="panel settings-card">
          <div className="settings-row">
            <div>
              <h3>高级功能</h3>
              <p>默认隐藏协作治理和专业制作工具，让创作流程保持简洁：</p>
              <ol className="workflow-chips" aria-label="基础创作流程">
                {SIMPLE_WORKFLOW.map((step, index) => <li key={step}><b>{index + 1}</b>{step}</li>)}
              </ol>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                role="switch"
                checked={advanced}
                aria-label="显示高级功能"
                onChange={(event) => {
                  setAdvanced(event.target.checked);
                  toast(event.target.checked ? "已显示高级功能" : "已隐藏高级功能，基础流程保持不变", "success");
                }}
              />
              <span>{advanced ? "已开启" : "已关闭"}</span>
            </label>
          </div>
          <div className={`advanced-feature-list${advanced ? " is-on" : ""}`}>
            <span>开启后显示：</span>
            <ul>
              {ADVANCED_FEATURES.map((item) => <li key={item}><Icon name={advanced ? "check" : "lock"} size={14} />{item}</li>)}
            </ul>
          </div>
        </div>
        {advanced && !session.publicMode && <AccountPanel />}
      </div>
    </section>
  );
}
