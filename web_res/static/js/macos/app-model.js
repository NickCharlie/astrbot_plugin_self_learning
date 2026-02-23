/**
 * 应用注册表
 * 每个应用作为 macOS 桌面上的一个窗口
 * 业务应用窗口默认 ~75% 视口大小，移动端自动全屏
 */
(function () {
  var vw = window.innerWidth || 1280;
  var vh = window.innerHeight || 800;
  // 业务应用默认 75% 视口
  var W = Math.round(vw * 0.75);
  var H = Math.round(vh * 0.75);
  // 最小 / 最大限制
  if (W < 360) W = 360;
  if (H < 400) H = 400;
  if (W > 1600) W = 1600;
  if (H > 1000) H = 1000;

  window.AppModel = {
    allAppList: [
      // === 系统应用 ===
      {
        key: "system_about",
        component: "SystemAbout",
        icon: "icon-question",
        title: "关于自学习插件",
        iconColor: "#fff",
        iconBgColor: "#23282d",
        width: 400,
        height: 280,
        disableResize: true,
        hideInDesktop: true,
        menu: [
          {
            key: "about",
            title: "关于",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "system_launchpad",
        component: "SystemLaunchPad",
        icon: "icon-appstore",
        title: "启动台",
        iconColor: "#333",
        iconBgColor: "#d4dbef",
        width: 500,
        height: 300,
        hideInDesktop: true,
        keepInDock: true,
      },
      {
        key: "system_setting",
        component: "SystemSetting",
        icon: "icon-setting",
        title: "系统偏好设置",
        iconColor: "#fff",
        iconBgColor: "#8e8e93",
        width: 700,
        height: 500,
        disableResize: true,
        hideInDesktop: false,
        keepInDock: true,
        menu: [
          {
            key: "setting",
            title: "偏好设置",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "system_task",
        component: "SystemTask",
        icon: "icon-icon_roundclose_fill",
        title: "强制退出...",
        iconColor: "#fff",
        iconBgColor: "#333",
        width: 300,
        height: 400,
        disableResize: true,
        hideInDesktop: true,
        menu: [
          {
            key: "task",
            title: "管理",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "system_calculator",
        component: "SystemCalculator",
        icon: "icon-changyongtubiao-mianxing-86",
        title: "计算器",
        iconColor: "#fff",
        iconBgColor: "#ff9500",
        width: 320,
        height: 480,
        disableResize: true,
        hideInDesktop: false,
        keepInDock: true,
      },
      // === 业务应用（全部在 Dock 中）===
      {
        key: "app_dashboard",
        component: "AppDashboard",
        icon: "icon-MIS_chanpinshezhi",
        title: "可视化大屏",
        iconColor: "#fff",
        iconBgColor: "#4b9efb",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "dashboard",
            title: "大屏",
            sub: [
              { key: "refresh_dashboard", title: "刷新数据" },
              { key: "close", title: "关闭" },
            ],
          },
        ],
      },
      {
        key: "app_persona_review",
        component: "AppPersonaReview",
        icon: "icon-MIS_bangongOA",
        title: "人格审查",
        iconColor: "#fff",
        iconBgColor: "#af52de",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "review",
            title: "审查",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "app_persona_mgmt",
        component: "AppPersonaManagement",
        icon: "icon-camera1",
        title: "人格管理",
        iconColor: "#fff",
        iconBgColor: "#34c759",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "persona",
            title: "管理",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "app_learning",
        component: "AppLearningStatus",
        icon: "icon-smallscreen_fill",
        title: "学习状态",
        iconColor: "#fff",
        iconBgColor: "#007aff",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "learning",
            title: "学习",
            sub: [
              { key: "relearn", title: "重新学习" },
              { key: "close", title: "关闭" },
            ],
          },
        ],
      },
      {
        key: "app_style",
        component: "AppStyleLearning",
        icon: "icon-wechat-fill",
        title: "对话风格学习",
        iconColor: "#fff",
        iconBgColor: "#5856d6",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "style",
            title: "风格",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "app_social",
        component: "AppSocialRelations",
        icon: "icon-github",
        title: "社交关系分析",
        iconColor: "#fff",
        iconBgColor: "#ff3b30",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "social",
            title: "社交",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "app_jargon",
        component: "AppJargonLearning",
        icon: "icon-gitee",
        title: "黑话学习",
        iconColor: "#fff",
        iconBgColor: "#ff9500",
        width: W,
        height: H,
        keepInDock: true,
        menu: [
          {
            key: "jargon",
            title: "黑话",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
      {
        key: "app_bug",
        component: "AppBugReport",
        icon: "icon-bug",
        title: "Bug 反馈",
        iconColor: "#fff",
        iconBgColor: "#ff2d55",
        width: Math.min(W, 700),
        height: H,
        hideInDesktop: false,
        keepInDock: true,
        menu: [
          { key: "bug", title: "反馈", sub: [{ key: "close", title: "关闭" }] },
        ],
      },
      {
        key: "app_performance",
        component: "AppPerformanceMonitor",
        icon: "icon-dashboard",
        title: "性能监控",
        iconColor: "#fff",
        iconBgColor: "#30d158",
        width: Math.min(W, 960),
        height: H,
        hideInDesktop: false,
        keepInDock: true,
        menu: [
          {
            key: "perf",
            title: "监控",
            sub: [{ key: "close", title: "关闭" }],
          },
        ],
      },
    ],
  };
})();
