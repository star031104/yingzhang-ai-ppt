import '@testing-library/jest-dom/vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { ModelsPage } from './ModelsPage';
import * as api from '../../api';
vi.mock('../../api', () => ({ discoverModels: vi.fn(), probeTextModel: vi.fn(), createProvider: vi.fn(), registerModel: vi.fn(), mapModelRole: vi.fn(), removeProvider: vi.fn(), testProvider: vi.fn(), testImageModel: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

test('pending image task can be queried again without showing a broken image', async () => {
  vi.mocked(api.testImageModel).mockResolvedValueOnce({ status: 'pending', message: '任务已保存，服务仍在生成' })
    .mockResolvedValueOnce({ status: 'ready', url: 'blob:fixture' });
  render(<ModelsPage providers={[{ id: 'p', name: '生图服务', base_url: 'https://example.com/v1' }]}
    models={[{ id: 'm', provider_id: 'p', model_id: 'Qwen/Qwen-Image', capabilities: ['image_generation'], quality_profile: {} }]}
    refresh={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '测试生图' }));
  expect(await screen.findByText(/任务已保存，服务仍在生成/)).toBeVisible();
  expect(screen.queryByAltText('生图模型测试结果')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '测试生图' }));
  expect(await screen.findByAltText('生图模型测试结果')).toHaveAttribute('src', 'blob:fixture');
  expect(api.testImageModel).toHaveBeenNthCalledWith(2, 'm');
});
test('empty filtered image catalog permits a manual model ID without inventing availability', async () => {
  vi.mocked(api.discoverModels).mockResolvedValue({ ok: true, models: [], latency_ms: 1 });
  render(<ModelsPage providers={[]} models={[]} refresh={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '生图模型' }));
  fireEvent.change(screen.getByLabelText('API 地址'), { target: { value: 'https://api-inference.modelscope.cn/v1' } });
  fireEvent.click(screen.getByRole('button', { name: /测试连接并获取模型/ }));
  const input = await screen.findByPlaceholderText('例如：Qwen/Qwen-Image');
  expect(screen.getByRole('button', { name: '保存并设为默认生图模型' })).toBeDisabled();
  fireEvent.change(input, { target: { value: 'Qwen/Qwen-Image' } });
  expect(screen.getByRole('button', { name: '保存并设为默认生图模型' })).toBeEnabled();
  expect(screen.getByText(/列表没有返回可识别的文生图模型/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('API 地址'), { target: { value: 'https://different.example/v1' } });
  expect(screen.queryByRole('button', { name: '保存并设为默认生图模型' })).not.toBeInTheDocument();
});

test('manual text model is probed before saving even when absent from discovery', async () => {
  vi.mocked(api.discoverModels).mockResolvedValue({ ok: true, models: ['glm-4.7'], latency_ms: 1 });
  vi.mocked(api.probeTextModel).mockResolvedValue({ ok: true, models: ['glm-4.7-flash'], latency_ms: 100 });
  vi.mocked(api.createProvider).mockResolvedValue({ id: 'p', name: '智谱', base_url: 'https://open.bigmodel.cn/api/paas/v4', has_api_key: true, enabled: true });
  vi.mocked(api.registerModel).mockResolvedValue({ id: 'm', provider_id: 'p', model_id: 'glm-4.7-flash', capabilities: ['chat'], quality_profile: {} });
  render(<ModelsPage providers={[]} models={[]} refresh={() => {}} />);
  fireEvent.change(screen.getByLabelText('API 地址'), { target: { value: 'https://open.bigmodel.cn/api/paas/v4' } });
  fireEvent.click(screen.getByRole('button', { name: /测试连接并获取模型/ }));
  fireEvent.change(await screen.findByPlaceholderText('例如：glm-4.7-flash'), { target: { value: 'glm-4.7-flash' } });
  fireEvent.click(screen.getByRole('button', { name: '验证模型并保存为默认工作模型' }));
  await waitFor(() => expect(api.registerModel).toHaveBeenCalledWith('p', 'glm-4.7-flash', expect.any(Array)));
  expect(api.probeTextModel).toHaveBeenCalledWith('https://open.bigmodel.cn/api/paas/v4', '', 'glm-4.7-flash');
});

test('failed text model probe does not save a provider', async () => {
  vi.mocked(api.discoverModels).mockResolvedValue({ ok: true, models: [], latency_ms: 1 });
  vi.mocked(api.probeTextModel).mockResolvedValue({ ok: false, models: [], latency_ms: 0, error: '无权限' });
  render(<ModelsPage providers={[]} models={[]} refresh={() => {}} />);
  fireEvent.change(screen.getByLabelText('API 地址'), { target: { value: 'https://open.bigmodel.cn/api/paas/v4' } });
  fireEvent.click(screen.getByRole('button', { name: /测试连接并获取模型/ }));
  fireEvent.change(await screen.findByPlaceholderText('例如：glm-4.7-flash'), { target: { value: 'glm-4.7-flash' } });
  fireEvent.click(screen.getByRole('button', { name: '验证模型并保存为默认工作模型' }));
  expect(await screen.findByText('模型验证失败：无权限')).toBeVisible();
  expect(api.createProvider).not.toHaveBeenCalled();
});
