import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, test, vi } from 'vitest';
import { ProjectEditor } from './ProjectEditor';
import { workflowStates } from './WorkflowStepper';
import { usePreferences } from '../../store/preferences';
import type { ProjectWorkspace } from '../../api';

const slide = { id: 's1', position: 1, revision: 1, role: 'cover', message: '结论', content: { title: '封面标题', bullets: ['要点'] } };
const workspace = {
  project: { id: 'p', name: '项目', status: 'ready' }, planOptions: {}, orchestration: {}, slides: [slide], candidates: [],
  sources: [], skillIds: [], gates: null, previewAvailable: false, sampleAvailable: false, exports: [], licensedAssets: [],
  brandAssets: [], members: [], approvals: [], publications: [], importedPowerPoint: null, evaluationRuns: [], narrative: null, designSystem: null,
} as unknown as ProjectWorkspace;

vi.mock('../../api', async (original) => ({
  ...(await original<typeof import('../../api')>()),
  getProjectWorkspace: vi.fn(() => Promise.resolve(workspace)),
  getSlideVersions: vi.fn(() => Promise.resolve([{ version: 1, reason: '初始', spec: slide }])),
  getSlideChat: vi.fn(() => Promise.resolve([])),
  getProfessionalPlatform: vi.fn(() => Promise.resolve(undefined)),
  validateProject: vi.fn(),
}));
afterEach(() => { cleanup(); usePreferences.setState({ advanced: false }); });

const renderEditor = () => render(
  <QueryClientProvider client={new QueryClient()}>
    <ProjectEditor projectId="p" skills={[]} back={() => {}} refreshProjects={() => {}} />
  </QueryClientProvider>,
);

test('新用户只看到基础流程，协作与发布等高级功能默认隐藏', async () => {
  renderEditor();
  expect(await screen.findByRole('list', { name: '创作流程' })).toBeInTheDocument();
  expect(screen.getByText(/高级功能已隐藏/)).toBeInTheDocument();
  expect(screen.queryByText('协作、审批与发布')).not.toBeInTheDocument();
  expect(screen.queryByText('PowerPoint 深度工作台')).not.toBeInTheDocument();
  expect(screen.getByText('品牌与素材')).toBeInTheDocument();
});

test('开启高级功能后显示治理与专业工具', async () => {
  usePreferences.setState({ advanced: true });
  renderEditor();
  expect(await screen.findByText('协作、审批与发布')).toBeInTheDocument();
  expect(screen.getByText('PowerPoint 深度工作台')).toBeInTheDocument();
});

test('流程状态按项目进度推进', () => {
  expect(workflowStates(workspace, null, false)).toMatchObject({ sources: 'optional', outline: 'done', generate: 'current', quality: 'todo' });
  const generated = { ...workspace, previewAvailable: true } as ProjectWorkspace;
  expect(workflowStates(generated, { passed: false } as never, false)).toMatchObject({ generate: 'done', edit: 'done', quality: 'warning' });
});
