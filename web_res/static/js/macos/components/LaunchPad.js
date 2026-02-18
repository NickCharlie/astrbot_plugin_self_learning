/**
 * MacOSLaunchPad - Full-screen app launcher grid overlay.
 * Shows all non-hidden desktop apps in a grid.
 * Single-click opens app and closes launchpad. Includes MacOSDock at the bottom.
 */
window.MacOSLaunchPad = {
  template: `
    <div class="macos-launchpad">
      <div class="body" @click.self="$store.commit('launchpad')">
        <div class="launchpad-app">
          <template v-for="item in deskTopAppList" :key="item.key">
            <div
              class="app-item"
              @click="openAndClose(item)"
              v-if="!item.hideInDesktop"
            >
              <div class="icon">
                <i
                  :style="{
                    backgroundColor: item.iconBgColor,
                    color: item.iconColor,
                  }"
                  class="iconfont"
                  :class="item.icon"
                ></i>
              </div>
              <div class="title">{{ item.title }}</div>
            </div>
          </template>
        </div>
      </div>
      <MacOSDock></MacOSDock>
    </div>
  `,
  data() {
    return {
      deskTopAppList: [],
    };
  },
  created() {
    this.deskTopAppList = window.MacOSTool.getDeskTopApp();
    this.$store.commit("getDockAppList");
  },
  methods: {
    openAndClose(item) {
      this.$store.commit("openApp", item);
      this.$store.commit("launchpad");
    },
    launchpad() {
      this.$emit("launchpad", this.$store.state.launchpad);
    },
  },
};
