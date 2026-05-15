/**
 * ECharts 按需引入注册（spec §4.1）。
 *
 * 只引入项目里实际用到的渲染器、图表类型和组件 —— 别 import 'echarts' 全量包，
 * 那样 bundle 会大 ~700KB gzip。按需引入实测 +220KB gzip 可接受。
 *
 * 任何 chart 组件文件顶部都要 import 这个模块一次（副作用注册），否则会运行
 * 时报 "Chart type 'line' should be registered"。
 */
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
]);
