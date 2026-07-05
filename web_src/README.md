# Self Learning Dashboard（Solid.js）

这里是独立 WebUI Dashboard 的新前端源码，使用 Solid.js、TypeScript、SCSS、Vite 和 ECharts。

> 生产接入说明：执行 `pnpm build` 后，产物会直接输出到仓库的 `web_res/static/dashboard/`（`index.html` 与 `assets/`），并由 Quart 以 `/static/dashboard/` 路径提供服务。后端 `webui/blueprints/auth.py` 的 Dashboard 入口（`/api/`、`/api/index`）会返回新版 SPA；若产物缺失则返回带自动刷新的 503 构建提示页，不再回退到旧版 `web_res/static/html/dashboard.html`。构建产物需要随仓库提交，以便无 Node 环境的用户开箱即用。`pages/dashboard` 下的 AstrBot 嵌入页不属于本前端。

## 环境与命令

推荐 Node.js 22 和 pnpm 10：

```powershell
pnpm install
pnpm dev
```

开发服务器默认运行在 `http://localhost:3000`，并把 `/api` 和 `/static` 代理到 `http://127.0.0.1:7833`。先启动插件 WebUI，即可使用真实数据开发。

如果后端地址不同：

```powershell
$env:VITE_DASHBOARD_PROXY="http://127.0.0.1:8989"
pnpm dev
```

质量检查：

```powershell
pnpm typecheck
pnpm test
pnpm build
```

`vite.config.ts` 将生产 `outDir` 指向 `../web_res/static/dashboard`，因此 `pnpm build` 的产物会直接落入插件静态目录并随仓库提交；本地构建中间目录 `dist/`（若存在）仍被忽略。

## 目录结构

```text
src/
  app/                 应用入口与页面切换
  components/
    ui/                按钮、表单、面板、分页等基础组件
    business/          审查、配置、图谱和融合组件
    charts/            ECharts 生命周期封装
    feedback/          Toast 与确认弹窗
    layout/            顶栏、导航和页面标题
  lib/                 格式化、diff、配置归一化和 hash 路由
  pages/               13 个 Dashboard 页面
  services/            类型化 HTTP 请求层
  stores/              Dashboard 全局状态和自动刷新
  styles/              SCSS tokens、mixins 和全局样式
  types/               API 与 UI TypeScript 类型
```

## 行为约定

- 页面地址继续使用 `#/page-name`，与旧 Dashboard 书签兼容。
- 主题使用 `sl-dashboard-theme`，pip 镜像使用 `sl-pip-mirror` 存入 localStorage。
- Dashboard 每 60 秒静默刷新；编辑内容或执行写操作时暂停自动刷新。
- 删除、批量审查、人格恢复和依赖安装都必须经过应用内确认框。
- 图表通过 `ResizeObserver` 自适应，组件销毁时同步释放 ECharts 实例。
- 不新增或修改后端 API；所有 endpoint 与旧 Dashboard 保持一致。
