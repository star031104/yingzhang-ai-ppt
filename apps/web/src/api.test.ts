import { afterEach, expect, test, vi } from 'vitest';
import { approveOutline } from './api';
afterEach(() => vi.unstubAllGlobals());
test('outline connection failure explains local recovery and does not retry mutation', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
  vi.stubGlobal('fetch', fetch);
  await expect(approveOutline('project')).rejects.toThrow('启动项目.cmd');
  expect(fetch).toHaveBeenCalledTimes(1);
});
