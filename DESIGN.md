# 澄观设计系统

## V2 工作台

`/demo` 使用浅灰工作区、白色数据表、酒红色主要操作（#a32b36）和低饱和绿色条件说明。桌面208px导航，390px窄屏改为横向导航；原版仍使用下述墨绿主题。

表格采用AG Grid Community，50条服务端分页、全量筛选与排序。条件区与实际生效条件分开显示，比例的分子分母可核验，统计项支持下钻。技术详情默认收起，用户先看到问题、答案和业务条件。

## Scene and strategy

HR 负责人在明亮会议室向主管展示数据，投影需要高对比度与明确层级。浅色工作区、墨绿导航、低饱和中性色，翡翠绿仅用于主要操作与选中态。

## Tokens

背景 oklch(0.975 0.005 160)，内容面 oklch(0.995 0.003 160)，正文 oklch(0.24 0.02 165)，强调色 oklch(0.46 0.105 165)。图表绿色、蓝色、琥珀色分工明确。边框 1px，圆角 8–12px，无装饰阴影。

## Typography and layout

系统中文 sans，正文 16px，标签 14px，次要信息 12px，标题 24–30px。桌面 228px 导航；顶部身份切换、模型状态和模拟数据标记。长表分页。

## Components and behavior

复用已安装 shadcn/Base UI sidebar、select、tabs、table、button、sheet、skeleton。图表有表格替代。请求显示阶段，失败保留输入，切换身份清空旧结果。动效只用 opacity/transform，尊重 prefers-reduced-motion。
