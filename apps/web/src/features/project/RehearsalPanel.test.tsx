import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import * as api from '../../api';
import { RehearsalPanel } from './RehearsalPanel';
import { GuidedIntakeDialog } from '../create/GuidedIntakeDialog';

vi.mock('../../api', () => ({
  buildRehearsal: vi.fn(),
  rehearsalCardUrl: (id: string) => `/api/v1/projects/${id}/rehearsal/card`,
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test('排练卡展示每页预算与有出处的问答', async () => {
  vi.mocked(api.buildRehearsal).mockResolvedValue({
    version: 'rehearsal-v1', durationMinutes: 10, advice: ['第 3 页讲稿超出时间预算'],
    pacing: { totalSeconds: 600, requestedSeconds: 600, naturalSeconds: 700, pages: [
      { position: 1, slideId: 's1', title: '封面', startSeconds: 0, budgetSeconds: 30, naturalSeconds: 20, pressure: 'ok' },
      { position: 3, slideId: 's3', title: '数据', startSeconds: 30, budgetSeconds: 90, naturalSeconds: 140, pressure: 'compress' },
    ] },
    questions: [{ kind: 'definition', position: 3, question: '12% 是怎么算的？', answer: '原文：转化率提升 12%', sourceRef: { document: 'a.md', section: 'S002' } }],
  });
  const jump = vi.fn();
  render(<RehearsalPanel projectId="p" onJumpToSlide={jump} />);
  fireEvent.click(screen.getByRole('button', { name: '生成排练卡' }));
  expect(await screen.findByText('12% 是怎么算的？')).toBeInTheDocument();
  expect(screen.getByText(/出处：a.md · S002/)).toBeInTheDocument();
  expect(screen.getByText(/需压缩/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '数据' }));
  expect(jump).toHaveBeenCalledWith('s3', 3);
  expect(screen.getByRole('link', { name: '下载排练卡' })).toHaveAttribute('href', '/api/v1/projects/p/rehearsal/card');
});

test('引导模式逐步确认并提交建议答案', () => {
  const confirm = vi.fn();
  render(<GuidedIntakeDialog busy={false} onCancel={vi.fn()} onConfirm={confirm} intake={{
    version: 'v', title: 't', preset: 'business', materialFacts: 1, phases: [
      { id: 'strategy', title: '策略', hint: 'h', questions: [{ id: 'audience', label: '主要受众是谁？', type: 'text', suggested: '管理层' }] },
      { id: 'substance', title: '内容', hint: 'h', questions: [{ id: 'mustCover', label: '必须讲到的关键事实', type: 'multi', suggested: ['F1'], options: [{ value: 'F1', label: '收入增长 12%' }, { value: 'F2', label: '成本下降 5%' }] }] },
    ] }} />);
  fireEvent.change(screen.getByLabelText('主要受众是谁？'), { target: { value: '董事会' } });
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  fireEvent.click(screen.getByLabelText('成本下降 5%'));
  fireEvent.click(screen.getByRole('button', { name: '确认并开始生成' }));
  expect(confirm).toHaveBeenCalledWith({ audience: '董事会', mustCover: ['F1', 'F2'] });
});
