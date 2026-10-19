import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { EvaluationPanel } from './EvaluationPanel';
import type { ResearchEvaluationRun } from '../../api';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const dimension = (score: number, rationale: string) => ({ score, rationale, source: 'rule', suggestions: [] });

const run: ResearchEvaluationRun = {
  id: 'run-1', suite: 'research-v1', status: 'completed', kinds: ['ppteval', 'quiz'],
  createdAt: '2026-10-19T00:00:00Z', stale: true, summary: { content: 4.6, design: 3.4, coherence: 4.8, retention: 72.2 },
  ppteval: {
    mode: 'rule', overall: 4.3, errors: [],
    deck: { content: dimension(4.6, '证据覆盖 100%'), design: dimension(3.4, '视觉成熟度 65 分'), coherence: dimension(4.8, '叙事节奏 90 分') },
    slides: [{
      position: 4, slideId: 'slide-4', title: '收入结构',
      content: { score: 5, rationale: '有材料来源', source: 'rule' },
      design: { score: 3, rationale: '发现：压缩观众文案', source: 'rule' },
      coherence: { score: 5, rationale: '衔接自然', source: 'rule' },
      issues: [{ dimension: 'design', code: 'long-audience-bullet', message: '压缩观众文案', suggestion: '每个要点只保留一个判断' }],
    }],
  },
  quiz: {
    status: 'completed', generator: 'rule', answerer: 'lexical', retention: 72.2, detailRetention: 80, conceptRetention: 62.5, errors: [],
    questions: [
      { id: 'q1', type: 'detail', question: '收入增长了多少？', expected: '18%', answer: '91%', supportedBySlide: null, correct: false },
      { id: 'q2', type: 'concept', question: '核心观点是什么？', expected: '续约率高', answer: '续约率高', supportedBySlide: 3, correct: true },
    ],
    missingFacts: [{ claim: 'Revenue increased 18% across the sample period.', missingValues: ['18%'] }],
  },
};

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
    new Response(JSON.stringify(handler(url, init)), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

test('加载最近评测：显示三维评分、保留率、过期提示与跳页', async () => {
  mockFetch((url) => (url.endsWith('/evaluations') ? [{ ...run, ppteval: undefined, quiz: undefined }] : run));
  const jump = vi.fn();
  render(<EvaluationPanel projectId="p1" slides={[{ id: 'slide-4', position: 4 }]} onJumpToSlide={jump} />);
  expect(await screen.findByText('内容已修改，结果已过期')).toBeInTheDocument();
  expect(screen.getByText('4.6')).toBeInTheDocument();
  expect(screen.getByText('3.4')).toBeInTheDocument();
  expect(screen.getByText('72.2%')).toBeInTheDocument();
  expect(screen.getByText(/缺少 18%/)).toBeInTheDocument();
  expect(screen.getByText('查看未答对的 1 道题')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '跳到该页' }));
  expect(jump).toHaveBeenCalledWith('slide-4', 4);
});

test('运行评测时提交所选类型，并提示缺少 PPTX 导出', async () => {
  const fetchMock = mockFetch((url, init) => {
    if (init?.method === 'POST') {
      return { ...run, stale: false, kinds: ['quiz', 'render'], ppteval: undefined,
        render: { status: 'no-export', pages: [], issues: [] } };
    }
    return [];
  });
  render(<EvaluationPanel projectId="p1" />);
  fireEvent.click(screen.getByLabelText('三维评分（PPTEval）'));
  fireEvent.click(screen.getByLabelText('PPTX 实际页面复核'));
  fireEvent.click(screen.getByRole('button', { name: '运行评测' }));
  expect(await screen.findByText('与当前内容一致')).toBeInTheDocument();
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(JSON.parse(String(post?.[1]?.body))).toEqual({ kinds: ['quiz', 'render'], use_models: true });
  expect(screen.getByText(/尚无 PPTX 导出/)).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole('button', { name: '跳到该页' })).not.toBeInTheDocument());
});
