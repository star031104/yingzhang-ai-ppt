import '@testing-library/jest-dom/vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { QualityCenter } from './QualityCenter';
import type { QualityReport } from '../../api';

afterEach(cleanup);
const report: QualityReport = {
  passed: false, contentCoverage: 1, blockingErrors: 1,
  professionalAudit: { overall: 90, grade: 'A', ready: false, dimensions: {}, recommendations: [] },
  visualQA: { checked: 2, expected: 3, blocking: 1, complete: false, missingPositions: [3],
    slides: [{ position: 2, issues: [{ code: 'text-clipped', message: '文字被容器或画布裁切' }] }] },
};

test('未渲染页面和文字裁切可见，高分不冒充可交付', () => {
  render(<QualityCenter report={report} />);
  expect(screen.getByText('页面显示检查 2/3 页')).toBeInTheDocument();
  expect(screen.getByText(/待生成第 3 页/)).toBeInTheDocument();
  expect(screen.getByText(/文字被容器或画布裁切/)).toBeInTheDocument();
  expect(screen.getByText(/检查尚未全部通过/)).toBeInTheDocument();
  expect(screen.queryByText(/已通过当前自动检查/)).not.toBeInTheDocument();
});

test('全部检查通过才展示通过状态', () => {
  render(<QualityCenter report={{ ...report, passed: true, blockingErrors: 0,
    professionalAudit: { ...report.professionalAudit!, ready: true },
    visualQA: { checked: 3, expected: 3, blocking: 0, complete: true },
  }} />);
  expect(screen.getByText(/已通过当前自动检查/)).toBeInTheDocument();
});

test('修改后的页面明确提示重新生成', () => {
  render(<QualityCenter report={{ ...report, visualQA: { ...report.visualQA!, stalePositions: [2] } }} />);
  expect(screen.getByText(/第 2 页已修改，需重新生成/)).toBeInTheDocument();
  expect(screen.queryByText(/已通过当前自动检查/)).not.toBeInTheDocument();
});
