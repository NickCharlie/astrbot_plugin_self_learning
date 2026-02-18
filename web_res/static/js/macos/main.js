/**
 * MacOS Web UI - 主入口
 * 创建 Vue 实例，注册所有组件，挂载应用
 */
(function () {
  const { createApp } = Vue;
  const { createStore } = Vuex;

  // 创建 Vue 应用
  const app = createApp(window.MacOSRoot);

  // 安装 Element Plus（中文）
  app.use(ElementPlus, {
    locale: window.ElementPlusLocaleZhCn,
  });

  // 创建并安装 Vuex Store
  const store = createStore(window.MacOSStoreConfig);
  app.use(store);

  // 注入全局工具
  app.config.globalProperties.tool = window.MacOSTool;
  app.config.globalProperties.config = {
    debug: false,
    apiBaseUrl: "",
    version: 10000,
    defaultErrorMessage: "请求服务器失败,请稍后再试",
  };

  // === 注册框架组件 ===
  app.component("MacOSBg", window.MacOSBg);
  app.component("MacOSLoading", window.MacOSLoading);
  app.component("MacOSLogin", window.MacOSLogin);
  app.component("MacOSDeskTop", window.MacOSDeskTop);
  app.component("MacOSAppWindow", window.MacOSAppWindow);
  app.component("MacOSDock", window.MacOSDock);
  app.component("MacOSLaunchPad", window.MacOSLaunchPad);
  app.component("MacOSWidget", window.MacOSWidget);

  // === 注册系统应用 ===
  app.component("SystemAbout", window.SystemAbout);
  app.component("SystemSetting", window.SystemSetting);
  app.component("SystemTask", window.SystemTask);
  app.component("SystemCalculator", window.SystemCalculator);
  // SystemLaunchPad 不需要单独注册（由 LaunchPad 框架组件处理）

  // === 注册业务应用 ===
  app.component("AppDashboard", window.AppDashboard);
  app.component("AppPersonaReview", window.AppPersonaReview);
  app.component("AppPersonaManagement", window.AppPersonaManagement);
  app.component("AppLearningStatus", window.AppLearningStatus);
  app.component("AppStyleLearning", window.AppStyleLearning);
  app.component("AppSocialRelations", window.AppSocialRelations);
  app.component("AppJargonLearning", window.AppJargonLearning);
  app.component("AppBugReport", window.AppBugReport);

  // 挂载
  app.mount("#app");

  // 恢复保存的主题
  var savedTheme = localStorage.getItem("macos-theme");
  if (savedTheme) {
    document.documentElement.setAttribute("data-theme", savedTheme);
    document.body.setAttribute("data-theme", savedTheme);
    if (savedTheme === "dark") {
      document.body.style.colorScheme = "dark";
    }
  }

  // 调试信息
  console.log(
    "[MacOS Web UI] 应用已挂载，已注册组件:",
    Object.keys(app._context.components).length,
    "个",
  );
})();
