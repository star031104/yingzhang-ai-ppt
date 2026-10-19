import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import * as api from '../../api';
import { VideoExport } from './VideoExport';
import { ProposalReviewPanel, SlideProposalNote } from './ProposalReview';
import { SourceUnderstanding } from './SourceUnderstanding';
import type { ProjectWorkspace } from '../../api';

vi.mock('../../api', () => ({
  startNarratedVideoJob: vi.fn(),
  waitForProjectJob: vi.fn(),
  narratedVideoUrl: (id: string, subtitles = false) => `/api/v1/projects/${id}/export/video${subtitles ? '?subtitles=true' : ''}`,
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test('缺少 ffmpeg 时给出安装说明而不是原始报错', async () => {
  vi.mocked(api.startNarratedVideoJob).mockRejectedValue(new Error('未找到 ffmpeg；请安装 ffmpeg 或设置 YINGZHANG_FFMPEG 后再导出讲解视频'));
  render(<VideoExport projectId="p" />);
  fireEvent.click(screen.getByRole('button', { name: /讲解视频/ }));
  fireEvent.click(screen.getByRole('button', { name: /开始导出/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('YINGZHANG_FFMPEG');
  expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
});

test('任务完成后提供 MP4 与 SRT 下载', async () => {
  vi.mocked(api.startNarratedVideoJob).mockResolvedValue({ id: 'j' } as never);
  vi.mocked(api.waitForProjectJob).mockResolvedValue({ checkpoint: { result: { durationSeconds: 42, subtitles: '/x.srt', silentSlides: 0 } } } as never);
  render(<VideoExport projectId="p" />);
  fireEvent.click(screen.getByRole('button', { name: /讲解视频/ }));
  fireEvent.click(screen.getByRole('switch', { name: /语音配音/ }));
  fireEvent.click(screen.getByRole('button', { name: /开始导出/ }));
  expect(await screen.findByRole('link', { name: /下载 MP4/ })).toHaveAttribute('href', '/api/v1/projects/p/export/video');
  expect(screen.getByRole('link', { name: /下载 SRT 字幕/ })).toHaveAttribute('href', '/api/v1/projects/p/export/video?subtitles=true');
  expect(api.startNarratedVideoJob).toHaveBeenCalledWith('p', { tts: false, subtitles: true });
});

test('显示模型提议的自动修正与待确认的章节用途', () => {
  const issue = { position: 2, code: 'unsupported-number', severity: 'repaired', message: '出现事实白名单之外的数字，已替换或删除' };
  const slide = { id: 's2', position: 2, revision: 1, role: 'data', content: { title: '数据', bullets: [] }, proposalIssues: [issue] };
  const onJump = vi.fn();
  render(<>
    <SlideProposalNote slide={slide} />
    <ProposalReviewPanel data={{ slides: [slide], proposalValidation: { summary: { pages: 1, accepted: 0, repaired: 1, fallback: 0 }, issues: [issue], fallbackPositions: [] } } as unknown as ProjectWorkspace} onJump={onJump} />
    <SourceUnderstanding sources={[{ id: '1', name: 'a.pdf', sha256: 'x' }]} documents={[{ name: 'a.pdf', uncertainRoles: [{ title: '附录', role: 'evidence', confidence: 0.4 }] }]} />
  </>);
  expect(screen.getAllByText('已自动修正 1 处模型提议')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: '查看' }));
  expect(onJump).toHaveBeenCalledWith('s2');
  expect(screen.getByText(/1 个章节用途待确认/)).toBeInTheDocument();
  expect(screen.getByText('推测为证据 · 置信度 40%')).toBeInTheDocument();
});
