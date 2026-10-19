import { useState } from "react";
import { bindLicensedAsset, registerLicensedAsset, uploadBrandAsset } from "../../api";
import type { ProjectWorkspace, SlideSpec } from "../../api";

/** Licensed media ledger and brand logo upload for the current project. */
export function BrandAssetsPanel({
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
  const [assetFile, setAssetFile] = useState<File | null>(null),
    [assetName, setAssetName] = useState(""),
    [assetLicense, setAssetLicense] = useState("owned"),
    [assetAttribution, setAssetAttribution] = useState(""),
    [brandFile, setBrandFile] = useState<File | null>(null);
  return (
    <details className="panel p1-studio brand-assets">
      <summary><span><b>品牌与素材</b><small>上传品牌标识，登记有授权的图片、视频和音频</small></span><i>{(data.licensedAssets || []).length} 项素材</i></summary>
      <div className="p1-grid">
        <div className="p1-section">
          <b>合规素材</b>
          <input value={assetName} onChange={(event) => setAssetName(event.target.value)} placeholder="素材名称" aria-label="素材名称" />
          <div className="p1-row">
            <select value={assetLicense} onChange={(event) => setAssetLicense(event.target.value)} aria-label="授权方式"><option value="owned">自有版权</option><option value="internal">内部授权</option><option value="cc0">CC0</option><option value="cc-by">CC BY</option><option value="unsplash">Unsplash</option></select>
            <input value={assetAttribution} onChange={(event) => setAssetAttribution(event.target.value)} placeholder="作者 / 归属信息" aria-label="作者或归属信息" />
          </div>
          <input type="file" accept=".png,.jpg,.jpeg,.webp,.svg,.mp4,.webm,.mov,.mp3,.wav,.m4a" onChange={(event) => setAssetFile(event.currentTarget.files?.[0] || null)} aria-label="选择素材文件" />
          <button disabled={busy || !assetName.trim() || !assetFile} onClick={async () => {
            const kind = assetFile?.type.startsWith("video/") ? "video" : assetFile?.type.startsWith("audio/") ? "audio" : "image";
            setBusy(true);
            try {
              await registerLicensedAsset(projectId, { name: assetName, kind, provider: "uploaded", sourceUrl: "", license: assetLicense, attribution: assetAttribution, file: assetFile });
              await refresh();
              setAssetName(""); setAssetFile(null);
              setStatus(`${kind === "video" ? "视频" : kind === "audio" ? "音频" : "图片"}素材已登记到授权台账`);
            } catch (error) { setStatus(error instanceof Error ? error.message : "素材登记失败"); } finally { setBusy(false); }
          }}>登记素材</button>
          {(data.licensedAssets || []).map((asset) => (
            <div className="asset-ledger-row" key={asset.id}>
              <span><b>{asset.name}</b><small>{asset.license} · {asset.attribution || "自有"}</small></span>
              {current && asset.approved && <button className="btn-sm" onClick={async () => { await bindLicensedAsset(projectId, current.id, asset.id); await refresh(); setStatus("素材已绑定到当前页"); }}>用于当前页</button>}
            </div>
          ))}
        </div>
        <div className="p1-section">
          <b>品牌标识</b>
          <small className="field-help">上传后用于封面与页眉，PNG、JPG 或 SVG。</small>
          <input type="file" accept=".png,.jpg,.jpeg,.svg" onChange={(event) => setBrandFile(event.currentTarget.files?.[0] || null)} aria-label="选择品牌标识" />
          <button disabled={busy || !brandFile} onClick={async () => {
            if (!brandFile) return;
            setBusy(true);
            try { await uploadBrandAsset(projectId, brandFile.name, "logo", brandFile); await refresh(); setBrandFile(null); setStatus("品牌标识已加入项目资产库"); }
            catch (error) { setStatus(error instanceof Error ? error.message : "品牌资产上传失败"); }
            finally { setBusy(false); }
          }}>上传品牌标识</button>
        </div>
      </div>
    </details>
  );
}
