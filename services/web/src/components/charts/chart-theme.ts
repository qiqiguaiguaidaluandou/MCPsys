/**
 * 图表配色 —— 与 `styles/tokens.scss` 的 CSS variable 同步。
 *
 * ECharts option 字段都是普通字符串/对象，不接 CSS var()，所以这里把项目色板
 * 显式落成 hex 值。运行期还多读一次 CSS var 做兜底（万一以后用户切了主题），
 * 失败回 fallback。tokens.scss 改色时，把 fallback 也一起改。
 */
import type { Metric } from '@/api/stats';

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined' || !window.document) return fallback;
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch {
    return fallback;
  }
}

export const COLORS = {
  primary: () => cssVar('--color-primary-500', '#3B82F6'),
  primaryBg: () => cssVar('--color-primary-50', '#EFF6FF'),
  success: () => cssVar('--color-success', '#10B981'),
  warning: () => cssVar('--color-warning', '#F59E0B'),
  error: () => cssVar('--color-error', '#EF4444'),
  info: () => cssVar('--color-info', '#6366F1'),
  gray100: () => cssVar('--color-gray-100', '#F1F5F9'),
  gray200: () => cssVar('--color-gray-200', '#E2E8F0'),
  gray400: () => cssVar('--color-gray-400', '#94A3B8'),
  gray500: () => cssVar('--color-gray-500', '#64748B'),
  gray700: () => cssVar('--color-gray-700', '#334155'),
};

/** metric 决定主色：错误类 = 红，限流 = 黄，其余 = 蓝。 */
export function metricColor(metric: Metric): string {
  if (metric === 'errors' || metric === 'error_rate') return COLORS.error();
  if (metric === 'throttled') return COLORS.warning();
  return COLORS.primary();
}

/** tooltip 默认样式，所有 chart 共用。 */
export function tooltipBase() {
  return {
    backgroundColor: cssVar('--color-surface', '#FFFFFF'),
    borderColor: COLORS.gray200(),
    borderWidth: 1,
    textStyle: { color: COLORS.gray700(), fontSize: 12 },
    extraCssText:
      'box-shadow: 0 4px 8px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.05);',
  };
}
