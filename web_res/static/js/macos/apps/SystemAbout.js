/**
 * 关于自学习插件 - 系统应用
 * 包含 QQ 群和 GitHub 链接
 */
window.SystemAbout = {
  props: { app: Object },
  template: `
    <div style="width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:30px;box-sizing:border-box;text-shadow:none;color:#333;background:#f5f5f7;">
      <div style="width:80px;height:80px;border-radius:20px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;align-items:center;justify-content:center;margin-bottom:16px;">
        <i class="iconfont icon-apple-fill" style="font-size:48px;color:#fff;"></i>
      </div>
      <h2 style="margin:0 0 4px 0;font-size:18px;font-weight:600;">AstrBot 自学习插件</h2>
      <p style="margin:0 0 4px 0;font-size:12px;color:#86868b;">Self Learning Plugin for AstrBot</p>
      <p style="margin:0 0 20px 0;font-size:11px;color:#86868b;">macOS Web UI Edition</p>
      <div style="display:flex;flex-direction:column;gap:10px;width:100%;max-width:280px;">
        <a href="https://qm.qq.com/q/1021544792" target="_blank" rel="noopener"
           style="display:flex;align-items:center;gap:10px;padding:10px 16px;background:#fff;border-radius:10px;text-decoration:none;color:#333;border:1px solid #e5e5e5;cursor:pointer;transition:background 0.2s;">
          <span style="width:36px;height:36px;border-radius:8px;background:#12b7f5;display:flex;align-items:center;justify-content:center;">
            <i class="iconfont icon-wechat-fill" style="font-size:20px;color:#fff;"></i>
          </span>
          <div>
            <div style="font-size:14px;font-weight:500;">QQ 交流群</div>
            <div style="font-size:11px;color:#86868b;">1021544792</div>
          </div>
        </a>
        <a href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank" rel="noopener"
           style="display:flex;align-items:center;gap:10px;padding:10px 16px;background:#fff;border-radius:10px;text-decoration:none;color:#333;border:1px solid #e5e5e5;cursor:pointer;transition:background 0.2s;">
          <span style="width:36px;height:36px;border-radius:8px;background:#24292e;display:flex;align-items:center;justify-content:center;">
            <i class="iconfont icon-github" style="font-size:20px;color:#fff;"></i>
          </span>
          <div>
            <div style="font-size:14px;font-weight:500;">GitHub 仓库</div>
            <div style="font-size:11px;color:#86868b;">查看源代码 & Star</div>
          </div>
        </a>
      </div>
    </div>
  `
};
