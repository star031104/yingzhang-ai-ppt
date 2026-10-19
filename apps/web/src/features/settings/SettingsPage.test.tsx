import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SettingsPage } from './SettingsPage';
import { usePreferences } from '../../store/preferences';

afterEach(() => { cleanup(); usePreferences.setState({ theme: 'system', advanced: false }); document.documentElement.removeAttribute('data-theme'); window.localStorage.clear(); vi.restoreAllMocks(); });
const session = { authenticated: true, name: '本机管理员', role: 'admin' as const, publicMode: false };
vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ authenticated: true, privateMode: false }) })));
const renderPage = () => render(<QueryClientProvider client={new QueryClient()}><SettingsPage session={session} /></QueryClientProvider>);

test('高级功能默认关闭，开启后持久保存', () => {
  renderPage();
  const toggle = screen.getByRole('switch', { name: '显示高级功能' });
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  expect(usePreferences.getState().advanced).toBe(true);
  expect(JSON.parse(window.localStorage.getItem('yingzhang.ui-preferences.v1')!)).toMatchObject({ advanced: true });
  expect(screen.getByText('已开启')).toBeInTheDocument();
});

test('主题可手动切换，存储不可用时不报错', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
  renderPage();
  fireEvent.click(screen.getByRole('radio', { name: /深色/ }));
  expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  fireEvent.click(screen.getByRole('radio', { name: /跟随系统/ }));
  expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
});
