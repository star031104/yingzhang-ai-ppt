import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import type { ProjectWorkspace } from '../../api';
import { ProjectPreview } from './ProjectPreview';

afterEach(cleanup);

test('预览和检查草稿不经过正式交付门禁，正式下载仍使用门禁', () => {
  const data = { previewAvailable: true, sources: [], skillIds: [] } as unknown as ProjectWorkspace;
  render(<ProjectPreview projectId="sample" data={data} previewKey={7} busy={false}
    qualityReport={null} setBusy={() => {}} setStatus={() => {}} />);
  const preview = new URL(screen.getByTitle('演示预览').getAttribute('src')!, 'http://localhost');
  expect(preview.searchParams.get('stage')).toBe('draft');
  expect(preview.searchParams.get('preview')).toBe('7');
  expect(screen.getByRole('link', { name: '下载 PPTX' })).toHaveAttribute('href', expect.stringContaining('stage=final'));
  expect(screen.getByRole('link', { name: '下载检查草稿 PPTX' })).toHaveAttribute('href', expect.stringContaining('stage=draft'));
});
