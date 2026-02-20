<template>
  <div class="launchpad">
    <div class="body">
      <div class="launchpad-app">
        <template v-for="item in deskTopAppList" :key="item.key">
          <div
            class="app-item"
            v-on:dblclick="$store.commit('openApp', item)"
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
    <Dock></Dock>
  </div>
</template>

<script>
import Dock from "@/components/Dock";
export default {
  components: {
    Dock,
  },
  data() {
    return {
      deskTopAppList: [],
    };
  },
  created() {
    this.deskTopAppList = this.tool.getDeskTopApp();
    this.$store.commit("getDockAppList");
  },
  methods: {
    launchpad() {
      this.$emit("launchpad", this.$store.state.launchpad);
    },
  },
};
</script>

<style lang="scss" scoped>
.launchpad {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: white;
  margin-top: -100px;
  z-index: 99900;
  backdrop-filter: blur(100px);
  .body {
    flex-grow: 1;
    width: 100%;
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    position: relative;
    .launchpad-app {
      position: fixed;
      left: 10%;
      right: 5%;
      display: flex;
      flex-direction: row;
      justify-content: flex-start;
      align-items: flex-end;
      padding: 100px;
      flex-wrap: wrap;
      .app-item {
        padding: 10px 0px;
        flex-direction: column;
        text-align: center;
        text-shadow: 0px 0px 2px rgb(0 0 0 / 50%);
        cursor: pointer;
        border-radius: 10px;
        border: 2px solid transparent;
        justify-content: center;
        align-items: center;
        width: 180px;
        .icon {
          border-radius: 10px;
          display: flex;
          justify-content: center;
          align-items: center;
          text-align: center;
        }
        .iconfont {
          font-size: 100px;
          border-radius: 10px;
          padding: 8px;
        }
        .title {
          font-size: 12px;
          margin-top: 5px;
          white-space: nowrap;
          text-overflow: ellipsis;
          overflow: hidden;
        }
      }
    }
  }
  .footer {
    display: flex;
    z-index: 100;
    bottom: 0;
  }
}
</style>
