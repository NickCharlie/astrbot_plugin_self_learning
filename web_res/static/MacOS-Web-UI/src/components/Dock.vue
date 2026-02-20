<template>
  <div class="footer">
    <div class="space"></div>
    <div class="dock">
      <template v-for="item in $store.state.dockAppList" :key="item.pid">
        <div
          class="item"
          @click="openApp(item)"
          :class="$store.state.nowApp.pid == item.pid ? 'jump' : ''"
          v-if="item && tool.isAppInKeepList(item, $store.state.dockAppList)"
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
            v-if="tool.isAppInOpenList(item, $store.state.openAppList)"
          ></div>
          <div class="title">{{ item.title }}</div>
        </div>
      </template>
    </div>
    <div class="space"></div>
  </div>
</template>
<script>
export default {
  data() {
    return {};
  },
  methods: {
    openApp(item) {
      console.log(item);
      switch (item.key) {
        case "system_launchpad":
          this.$store.commit("launchpad");
          break;
        default:
          this.$store.commit("openApp", item);
          break;
      }
    },
  },
};
</script>

<style scoped lang="scss">
.dock {
  background-color: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(20px);
  border-radius: 10px;
  flex-direction: row;
  display: flex;
  padding: 2px;
  z-index: 99990;
  .item {
    padding: 3px;
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
    .iconfont {
      cursor: pointer;
      border-radius: 20px;
      padding: 2px;
      display: inline-block;
      background-color: rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      height: 30px;
      width: 30px;
      text-align: center;
      font-size: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.3s, margin 0.3s;
    }
  }
  .item:hover {
    .iconfont {
      transform: scale(2) translateY(-10px);
      margin: 0px 15px;
      box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.3);
    }
    .title {
      position: absolute;
      display: inherit;
      word-break: keep-all;
      background: rgba(0, 0, 0, 0.3);
      box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
      border-radius: 10px;
      padding: 5px 10px;
      font-size: 12px;
      animation: dockTitleAnimation 0.5s ease 1 forwards;
    }
  }
  .dot {
    width: 3px;
    height: 3px;
    background: rgba(0, 0, 0, 0.8);
    position: absolute;
    bottom: 0px;
    border-radius: 5px;
    display: inline-block;
    font-size: 0;
  }
  .title {
    display: none;
  }
  .jump {
    animation: jumpAnimation 0.8s ease 1;
  }
}
</style>
