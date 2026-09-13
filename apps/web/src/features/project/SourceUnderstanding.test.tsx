import '@testing-library/jest-dom/vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { SourceUnderstanding } from './SourceUnderstanding';

afterEach(cleanup);
test('读取不完整时显示原因和原文限制，不冒充已理解', () => {
  render(<SourceUnderstanding sources={[{ id: '1', name: '扫描报告.pdf', sha256: 'abc',
    readingStatus: 'needs-attention', sections: 2, tables: 1,
    readingWarnings: [{ code: 'ocr-required', page: 2, message: '第 2 页缺少可读取文字，需要文字识别或补充文本' }],
    outline: [{ id: 'S001', title: '结果', headingPath: ['报告', '结果'], mainPoint: '试点减少人工复核', limitations: ['仅限内部样本'] }],
  }]} />);
  expect(screen.getByText('1 份材料需要补充核对')).toBeInTheDocument();
  fireEvent.click(screen.getByText('材料读取情况'));
  expect(screen.getByText(/第 2 页缺少可读取文字/)).toBeVisible();
  expect(screen.getByText('报告 / 结果')).toBeInTheDocument();
  expect(screen.getByText('仅限内部样本')).toBeInTheDocument();
});
