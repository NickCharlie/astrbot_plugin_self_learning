/**
 * 强制退出 - 系统应用
 */
window.SystemTask = {
  props: { app: Object },
  computed: {
    openApps() {
      return this.$store.state.openAppList.filter(a => a.key !== 'system_task');
    }
  },
  methods: {
    forceQuit(app) {
      this.$store.commit('closeApp', app);
    },
    forceQuitAll() {
      const apps = [...this.$store.state.openAppList];
      apps.forEach(a => {
        if (a.key !== 'system_task') {
          this.$store.commit('closeApp', a);
        }
      });
    }
  },
  template: `
    <div style="width:100%;height:100%;display:flex;flex-direction:column;text-shadow:none;color:#333;background:#f5f5f7;">
      <div style="padding:16px 16px 8px;font-size:12px;color:#86868b;">
        选择要强制退出的应用程序：
      </div>
      <div style="flex:1;overflow-y:auto;padding:0 16px;">
        <div v-if="openApps.length === 0" style="text-align:center;padding:40px 0;color:#86868b;font-size:13px;">
          没有正在运行的应用
        </div>
        <div v-for="a in openApps" :key="a.pid"
             style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:#fff;border-radius:8px;margin-bottom:6px;border:1px solid #e5e5e5;cursor:pointer;"
             @click="forceQuit(a)">
          <i class="iconfont" :class="a.icon" :style="{fontSize:'18px',color:a.iconColor,backgroundColor:a.iconBgColor,borderRadius:'6px',padding:'4px',width:'26px',height:'26px',display:'flex',alignItems:'center',justifyContent:'center'}"></i>
          <span style="flex:1;font-size:13px;">{{ a.title }}</span>
          <span style="font-size:11px;color:#ff3b30;cursor:pointer;">退出</span>
        </div>
      </div>
      <div style="padding:12px 16px;border-top:1px solid #e5e5e5;">
        <button @click="forceQuitAll"
                style="width:100%;padding:8px;background:#ff3b30;color:#fff;border:none;border-radius:8px;font-size:13px;cursor:pointer;">
          全部强制退出
        </button>
      </div>
    </div>
  `
};
