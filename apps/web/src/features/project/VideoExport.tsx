import { useState } from "react";
import { narratedVideoUrl, startNarratedVideoJob, waitForProjectJob } from "../../api";
import type { NarratedVideoResult, ProjectJob } from "../../api";
import { Icon } from "../../components/Icon";
import { toast } from "../../store/toasts";

type Phase = "idle" | "running" | "done" | "error";

/** 导出讲解视频：讲稿 → 语音（可选）→ 逐页画面与字幕合成 MP4。 */
export function VideoExport({ projectId, disabled }: { projectId: string; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [tts, setTts] = useState(true);
  const [subtitles, setSubtitles] = useState(true);
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<ProjectJob | null>(null);
  const [result, setResult] = useState<NarratedVideoResult | null>(null);
  const [error, setError] = useState("");
  const missingFfmpeg = /ffmpeg/i.test(error);

  async function start() {
    setPhase("running");
    setError("");
    setResult(null);
    try {
      const done = await waitForProjectJob(await startNarratedVideoJob(projectId, { tts, subtitles }), setJob);
      setResult((done.checkpoint.result ?? {}) as NarratedVideoResult);
      setPhase("done");
      toast("讲解视频已生成", "success");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "讲解视频导出失败");
      setPhase("error");
    }
  }
  const percent = Math.max(2, Math.round((job?.progress ?? 0) * 100));
  return (
    <>
      <button
        type="button"
        className={`video-export-tile${open ? " active" : ""}`}
        aria-expanded={open}
        aria-controls="video-export-panel"
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="play" size={15} /><span>讲解视频</span><small>MP4 · 配音与字幕</small>
      </button>
      {open && (
        <div className="video-export" id="video-export-panel">
          <div className="video-export-head">
            <div>
              <b>导出讲解视频</b>
              <small>根据每页讲稿合成配音，逐页画面与字幕拼接成 MP4。尚未生成的讲稿会自动补齐。</small>
            </div>
            <button type="button" className="ghost icon-button btn-sm" aria-label="收起" onClick={() => setOpen(false)}><Icon name="x" size={14} /></button>
          </div>
          <div className="video-export-options">
            <label className="switch"><input type="checkbox" role="switch" checked={tts} disabled={phase === "running"} onChange={(event) => setTts(event.target.checked)} /><span>语音配音<small>需要在模型配置中启用“语音合成”，未启用时按字幕时长无声导出</small></span></label>
            <label className="switch"><input type="checkbox" role="switch" checked={subtitles} disabled={phase === "running"} onChange={(event) => setSubtitles(event.target.checked)} /><span>生成 SRT 字幕<small>可单独下载，也会作为字幕轨嵌入视频</small></span></label>
          </div>
          {phase === "running" && (
            <div className="video-export-progress" aria-live="polite">
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><i style={{ width: `${percent}%` }} /></div>
              <small><span className="spinner" />{job?.checkpoint.label || "正在排队…"}（{percent}%）</small>
            </div>
          )}
          {phase === "error" && (
            <div className={`notice ${missingFfmpeg ? "warning" : "error"}`} role="alert">
              <span><Icon name="alert" size={15} /></span>
              <p>{missingFfmpeg
                ? "本机没有找到 ffmpeg，暂时无法合成视频。请安装 ffmpeg（Windows 可运行 winget install Gyan.FFmpeg），或在 .env 中设置 YINGZHANG_FFMPEG 指向 ffmpeg 可执行文件，然后重启映章。"
                : error}</p>
            </div>
          )}
          {phase === "done" && (
            <div className="video-export-result">
              <span className="badge success"><Icon name="check" size={12} />已生成{result?.durationSeconds ? ` · ${Math.round(result.durationSeconds)} 秒` : ""}</span>
              {!!result?.silentSlides && <small>{result.silentSlides} 页没有配音（未启用语音合成或合成失败），按字幕时长播放。</small>}
              <div className="button-group">
                <a className="button primary btn-sm" href={narratedVideoUrl(projectId)}><Icon name="download" size={14} />下载 MP4</a>
                {result?.subtitles && <a className="button btn-sm" href={narratedVideoUrl(projectId, true)}><Icon name="file" size={14} />下载 SRT 字幕</a>}
              </div>
            </div>
          )}
          {phase !== "running" && (
            <div className="video-export-actions">
              <button type="button" className={phase === "done" ? "btn-sm" : "primary btn-sm"} disabled={disabled} onClick={start}>
                <Icon name={phase === "done" ? "refresh" : "play"} size={14} />{phase === "done" ? "重新导出" : phase === "error" ? "重试" : "开始导出"}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
