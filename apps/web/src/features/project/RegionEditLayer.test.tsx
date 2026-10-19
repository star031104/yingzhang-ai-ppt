import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../../api';
import { RegionEditLayer, toSlideBox } from './RegionEditLayer';

vi.mock('../../api', () => ({ SLIDE_WIDTH: 1280, SLIDE_HEIGHT: 720, regionEditSlide: vi.fn() }));

// jsdom has no PointerEvent; a MouseEvent carries the coordinates the layer needs.
if (!('PointerEvent' in window)) {
  class PointerEventPolyfill extends MouseEvent { pointerId: number; constructor(type: string, init: PointerEventInit = {}) { super(type, init); this.pointerId = init.pointerId ?? 1; } }
  Object.defineProperty(window, 'PointerEvent', { value: PointerEventPolyfill });
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 360, width: 640, height: 360, toJSON: () => ({}),
  } as DOMRect);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.mocked(api.regionEditSlide).mockReset(); });

function drag(layer: Element, from: [number, number], to: [number, number]) {
  fireEvent.pointerDown(layer, { clientX: from[0], clientY: from[1], button: 0, pointerId: 1 });
  fireEvent.pointerMove(layer, { clientX: to[0], clientY: to[1], pointerId: 1 });
  fireEvent.pointerUp(layer, { clientX: to[0], clientY: to[1], pointerId: 1 });
}

test('框选坐标换算到 1280×720 页面坐标', () => {
  expect(toSlideBox({ x: 0.25, y: 0.5, w: 0.5, h: 0.25 })).toEqual({ x: 320, y: 360, width: 640, height: 180 });
});

test('拖出矩形后输入指令，按页面坐标提交并回传结果', async () => {
  const result = { slide: {}, version: 3, region: { bbox: {}, targets: [] }, edited: [{ kind: 'title', operation: 'replace', label: '页面标题' }], render: null };
  vi.mocked(api.regionEditSlide).mockResolvedValue(result as never);
  const onEdited = vi.fn();
  render(<RegionEditLayer projectId="p" slideId="s" revision={2} onExit={() => {}} onEdited={onEdited} />);
  const layer = screen.getByRole('application');
  drag(layer, [32, 36], [352, 72]);
  const input = await screen.findByLabelText('想怎样修改这块区域？');
  fireEvent.change(input, { target: { value: '改为：新的标题' } });
  fireEvent.click(screen.getByRole('button', { name: /应用修改/ }));
  await waitFor(() => expect(onEdited).toHaveBeenCalledWith(result));
  expect(api.regionEditSlide).toHaveBeenCalledWith('p', 's', { x: 64, y: 72, width: 640, height: 72 }, '改为：新的标题', 2);
  expect(await screen.findByText('已修改：页面标题')).toBeInTheDocument();
});

test('过小的框选被忽略，服务端拒绝时保留输入并显示原因', async () => {
  vi.mocked(api.regionEditSlide).mockRejectedValue(new Error('框选区域内没有可编辑的标题、要点或图表，请重新框选'));
  render(<RegionEditLayer projectId="p" slideId="s" onExit={() => {}} onEdited={() => {}} />);
  const layer = screen.getByRole('application');
  drag(layer, [10, 10], [12, 12]);
  expect(screen.queryByLabelText('想怎样修改这块区域？')).not.toBeInTheDocument();
  drag(layer, [100, 100], [300, 200]);
  fireEvent.change(await screen.findByLabelText('想怎样修改这块区域？'), { target: { value: '删除这里' } });
  fireEvent.click(screen.getByRole('button', { name: /应用修改/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('请重新框选');
  expect(screen.getByLabelText('想怎样修改这块区域？')).toHaveValue('删除这里');
});
