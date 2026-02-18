/**
 * 系统偏好设置 - Light/Dark 主题切换、壁纸上传
 */
window.SystemSetting = {
  props: { app: Object },
  data() {
    return {
      currentTheme: localStorage.getItem("macos-theme") || "light",
      currentWallpaper:
        localStorage.getItem("macos-wallpaper") || "/static/img/bg.jpg",
      presetWallpapers: ["/static/img/bg.jpg"],
    };
  },
  methods: {
    setTheme(theme) {
      this.currentTheme = theme;
      localStorage.setItem("macos-theme", theme);
      document.documentElement.setAttribute("data-theme", theme);
      document.body.setAttribute("data-theme", theme);
      if (theme === "dark") {
        document.body.style.colorScheme = "dark";
      } else {
        document.body.style.colorScheme = "light";
      }
    },
    setWallpaper(url) {
      this.currentWallpaper = url;
      localStorage.setItem("macos-wallpaper", url);
      // 通知背景组件更新
      window.EventBus.emit("wallpaper-change", url);
    },
    uploadWallpaper(event) {
      const file = event.target.files[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        alert("请选择图片文件");
        return;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target.result;
        this.setWallpaper(dataUrl);
      };
      reader.readAsDataURL(file);
    },
  },
  template: `
    <div style="width:100%;height:100%;overflow-y:auto;padding:24px;box-sizing:border-box;text-shadow:none;color:#333;background:#f5f5f7;">
      <h3 style="margin:0 0 20px 0;font-size:16px;font-weight:600;">外观</h3>
      <div style="display:flex;gap:16px;margin-bottom:30px;">
        <div @click="setTheme('light')"
             :style="{cursor:'pointer',padding:'12px',borderRadius:'12px',border: currentTheme==='light' ? '2px solid #007aff' : '2px solid #e5e5e5',background:'#fff',textAlign:'center',width:'120px'}">
          <div style="height:60px;background:linear-gradient(180deg,#f5f5f7,#fff);border-radius:8px;margin-bottom:8px;border:1px solid #e5e5e5;"></div>
          <div style="font-size:13px;font-weight:500;">浅色</div>
        </div>
        <div @click="setTheme('dark')"
             :style="{cursor:'pointer',padding:'12px',borderRadius:'12px',border: currentTheme==='dark' ? '2px solid #007aff' : '2px solid #e5e5e5',background:'#fff',textAlign:'center',width:'120px'}">
          <div style="height:60px;background:linear-gradient(180deg,#1c1c1e,#2c2c2e);border-radius:8px;margin-bottom:8px;border:1px solid #e5e5e5;"></div>
          <div style="font-size:13px;font-weight:500;">深色</div>
        </div>
      </div>

      <h3 style="margin:0 0 20px 0;font-size:16px;font-weight:600;">桌面壁纸</h3>
      <div style="margin-bottom:16px;">
        <label style="display:inline-flex;align-items:center;gap:8px;padding:8px 16px;background:#007aff;color:#fff;border-radius:8px;cursor:pointer;font-size:13px;">
          <span>上传壁纸</span>
          <input type="file" accept="image/*" @change="uploadWallpaper" style="display:none;" />
        </label>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <div v-for="wp in presetWallpapers" :key="wp" @click="setWallpaper(wp)"
             :style="{width:'140px',height:'90px',borderRadius:'8px',backgroundImage:'url('+wp+')',backgroundSize:'cover',backgroundPosition:'center',cursor:'pointer',border: currentWallpaper===wp ? '3px solid #007aff' : '3px solid transparent'}">
        </div>
      </div>

      <h3 style="margin:30px 0 16px 0;font-size:16px;font-weight:600;">关于</h3>
      <div style="padding:12px 16px;background:#fff;border-radius:10px;border:1px solid #e5e5e5;">
        <div style="display:flex;justify-content:space-between;padding:6px 0;font-size:13px;">
          <span style="color:#86868b;">QQ 交流群</span>
          <a href="https://qm.qq.com/q/1021544792" target="_blank" style="color:#007aff;text-decoration:none;">1021544792</a>
        </div>
        <div style="display:flex;justify-content:space-between;padding:6px 0;font-size:13px;border-top:1px solid #f0f0f0;">
          <span style="color:#86868b;">GitHub</span>
          <a href="https://github.com/NickCharlie/astrbot_plugin_self_learning" target="_blank" style="color:#007aff;text-decoration:none;">查看仓库</a>
        </div>
      </div>
    </div>
  `,
};
