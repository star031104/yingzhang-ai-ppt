import { useEffect, useState } from "react";
import { rollbackSlide } from "../../api";
import type { SlideSpec } from "../../api";
import { Icon } from "../../components/Icon";

type Version = { version: number; reason: string };
type Navigation = { slideId: string; cursorVersion: number; expectedCurrentVersion: number; redoVersions: number[] };

export function VersionPanel({
  projectId,
  current,
  versions,
  chat,
  busy,
  setBusy,
  setStatus,
  refresh,
}: {
  projectId: string;
  current?: SlideSpec;
  versions: Version[];
  chat: { id: string; actor: string; instruction: string; version: number }[];
  busy: boolean;
  setBusy: (busy: boolean) => void;
  setStatus: (status: string) => void;
  refresh: () => Promise<unknown>;
}) {
  const [navigation, setNavigation] = useState<Navigation | null>(null);
  useEffect(() => setNavigation(null), [current?.id]);
  const matches = Boolean(current && navigation?.slideId === current.id && navigation.expectedCurrentVersion === current.revision);
  const cursor = matches ? navigation!.cursorVersion : current?.revision ?? 0;
  const redoVersions = matches ? navigation!.redoVersions : [];
  const firstVersion = versions[0]?.version ?? 1;
  const canUndo = Boolean(current && cursor > firstVersion && versions.some((version) => version.version === cursor - 1));
  const canRedo = Boolean(current && redoVersions.length > 0 && versions.some((version) => version.version === redoVersions.at(-1)));
  const latest = versions.at(-1)?.version ?? 0;

  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true);
    try { await action(); }
    catch (error) { setStatus(error instanceof Error ? error.message : failure); }
    finally { setBusy(false); }
  }
  const undo = () => run(async () => {
    if (!current || !canUndo) return;
    const previous = versions.find((version) => version.version === cursor - 1);
    if (!previous) throw new Error("没有可撤销的上一版本");
    const result = await rollbackSlide(projectId, current.id, previous.version, current.revision);
    setNavigation({ slideId: current.id, cursorVersion: previous.version, expectedCurrentVersion: result.version, redoVersions: [...redoVersions, cursor] });
    await refresh();
    setStatus(`已撤销到版本 ${previous.version}`);
  }, "撤销失败");
  const redo = () => run(async () => {
    if (!current || !navigation || !matches || !canRedo) return;
    const target = navigation.redoVersions.at(-1)!;
    const result = await rollbackSlide(projectId, current.id, target, current.revision);
    setNavigation({ slideId: current.id, cursorVersion: target, expectedCurrentVersion: result.version, redoVersions: navigation.redoVersions.slice(0, -1) });
    await refresh();
    setStatus(`已重做到版本 ${target} 的内容（新版本 ${result.version}）`);
  }, "重做失败");

  return (
    <div className="version-panel">
      <div className="inspector-section-head">
        <div><b>版本记录</b><small>每次修改都会生成可回退的新版本</small></div>
        <div className="button-group">
          <button type="button" className="btn-sm" disabled={busy || !canUndo} onClick={undo}><Icon name="history" size={14} />撤销</button>
          <button type="button" className="btn-sm" disabled={busy || !canRedo} onClick={redo}>重做</button>
        </div>
      </div>
      <ol className="version-list">
        {versions.slice().reverse().map((version) => (
          <li key={version.version} className={version.version === latest ? "is-current" : ""}>
            <span className="version-dot" aria-hidden="true" />
            <div>
              <span>版本 {version.version}{version.version === latest && <em>当前</em>}</span>
              <small>{version.reason}</small>
            </div>
            <button
              type="button"
              className="ghost btn-sm"
              disabled={busy || version.version === latest}
              onClick={() => run(async () => {
                if (!current) return;
                await rollbackSlide(projectId, current.id, version.version, current.revision);
                setNavigation(null);
                await refresh();
                setStatus(`已回退到版本 ${version.version}`);
              }, "恢复历史版本失败")}
            >恢复</button>
          </li>
        ))}
      </ol>
      {chat.length > 0 && (
        <div className="chat-history">
          <b>最近的页内修改</b>
          {chat.slice(-4).reverse().map((item) => (
            <p key={item.id}><span>{item.instruction}</span><small>{item.actor} · 版本 {item.version}</small></p>
          ))}
        </div>
      )}
    </div>
  );
}
