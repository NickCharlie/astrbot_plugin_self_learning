/**
 * MacOSDock - Dock bar at the bottom of the desktop.
 * Shows dockAppList from Vuex store with icon hover animations,
 * active dot indicator, and title popup on hover.
 * Special handling for system_launchpad key (toggles launchpad).
 */
window.MacOSDock = {
  template: `
    <div class="macos-footer">
      <div class="space"></div>
      <div class="macos-dock">
        <template v-for="item in $store.state.dockAppList" :key="item.pid">
          <div
            class="item"
            @click="openApp(item)"
            :class="$store.state.nowApp && $store.state.nowApp.pid == item.pid ? 'jump' : ''"
            v-if="item && isAppInKeepList(item)"
          >
            <i
              :style="{
                backgroundColor: item.iconBgColor,
                color: item.iconColor,
              }"
              class="iconfont"
              :class="item.icon"
            ></i>
            <div
              class="dot"
              v-if="isAppInOpenList(item)"
            ></div>
            <div class="title">{{ item.title }}</div>
          </div>
        </template>
      </div>
      <div class="space"></div>
    </div>
  `,
  data() {
    return {};
  },
  methods: {
    isAppInKeepList(item) {
      return window.MacOSTool.isAppInKeepList(item, this.$store.state.dockAppList);
    },
    isAppInOpenList(item) {
      return window.MacOSTool.isAppInOpenList(item, this.$store.state.openAppList);
    },
    openApp(item) {
      switch (item.key) {
        case 'system_launchpad':
          this.$store.commit('launchpad');
          break;
        default:
          this.$store.commit('openApp', item);
          break;
      }
    }
  }
};
