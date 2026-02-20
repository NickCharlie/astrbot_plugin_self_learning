<template>
  <div class="desktop">
    <div class="top">
      <el-dropdown trigger="click">
        <div class="logo">
          <i class="iconfont icon-apple1"></i>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="openAppByKey('system_about')">
              <div>关于本站</div>
            </el-dropdown-item>
            <el-dropdown-item class="line"></el-dropdown-item>
            <el-dropdown-item @click="openAppByKey('system_setting')">
              <div>系统偏好设置</div>
            </el-dropdown-item>
            <el-dropdown-item @click="openAppByKey('system_store')">
              <div>应用商店</div>
            </el-dropdown-item>
            <el-dropdown-item class="line"></el-dropdown-item>
            <el-dropdown-item @click="openAppByKey('system_task')">
              <div>强制退出...</div>
            </el-dropdown-item>
            <el-dropdown-item class="line"></el-dropdown-item>
            <el-dropdown-item @click="shutdown">
              <div>关机...</div>
            </el-dropdown-item>
            <el-dropdown-item class="line"></el-dropdown-item>
            <el-dropdown-item @click="lockScreen">
              <div>锁定屏幕</div>
            </el-dropdown-item>
            <el-dropdown-item @click="logout">
              <div>退出登录 {{ userName }}...</div>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <div class="menu" v-for="item in menu" :key="item.value">
        <el-dropdown trigger="click" placement="bottom-start">
          <div class="item">{{ item.title }}</div>
          <template #dropdown>
            <el-dropdown-menu>
              <template v-for="subItem in item.sub" :key="subItem.value">
                <el-dropdown-item
                  class="line"
                  v-if="subItem.isLine"
                ></el-dropdown-item>
                <el-dropdown-item
                  v-else
                  @click="$store.commit('openMenu', subItem.key)"
                >
                  <div>{{ subItem.title }}</div>
                </el-dropdown-item>
              </template>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="space"></div>
      <div class="status">
        <div class="audio">
          <i
            class="iconfont icon-changyongtubiao-xianxingdaochu-zhuanqu-39"
            @click="showOrHideVolumn"
          ></i>

          <transition name="fade">
            <el-slider
              v-show="isVolumnShow"
              v-model="volumn"
              :show-tooltip="false"
              vertical
            ></el-slider>
          </transition>
        </div>
        <div class="datetime" @click.self="showOrHideCalendar">
          {{ timeString }}
          <transition name="fade">
            <el-calendar v-model="nowDate" v-if="isCalendarShow"></el-calendar>
          </transition>
        </div>
        <div class="notification">
          <i
            class="iconfont icon-changyongtubiao-xianxingdaochu-zhuanqu-25"
            @click="showOrHideWidget"
          ></i>
        </div>
      </div>
    </div>
    <div
      class="body"
      @contextmenu.prevent.self="
        hideAllController();
        openMenu($event);
      "
      @click.stop="hideAllController()"
    >
      <div class="desktop-app">
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
      <transition-group name="fade-window">
        <template v-for="item in $store.state.openAppList" :key="item.pid">
          <App
            v-if="!item.outLink"
            v-show="!item.hide"
            :app="item"
            :key="item.pid"
          ></App>
        </template>
      </transition-group>
      <transition name="fade-menu">
        <div
          v-show="rightMenuVisible"
          :style="{ left: rightMenuLeft + 'px', top: rightMenuTop + 'px' }"
          class="contextmenu"
        >
          <div @click="lockScreen">锁定屏幕...</div>
          <hr />
          <div @click="openAppByKey('system_setting')">系统偏好设置...</div>
          <div @click="openAppByKey('system_task')">强制退出...</div>
          <hr />
          <div @click="$message.warning('即将上线，敬请期待')">设置壁纸...</div>
          <div @click="openAppByKey('system_about')">关于我们</div>
        </div>
      </transition>
      <transition-group name="fade-widget">
        <div v-show="isWidgetShow">
          <template v-for="item in $store.state.openWidgetList" :key="item.pid">
            <Widget
              v-if="!item.outLink"
              v-show="!item.hide"
              :app="item"
              :key="item.pid"
            ></Widget>
          </template>
        </div>
      </transition-group>
    </div>
    <Dock></Dock>
  </div>
</template>
<script>
import App from "@/components/App";
import Dock from "@/components/Dock";
import Widget from "@/components/Widget";
export default {
  components: {
    App,
    Dock,
    Widget,
  },
  data() {
    return {
      isCalendarShow: false,
      nowDate: new Date(),
      volumnDelayTimer: false,
      volumn: 80,
      isVolumnShow: false,
      rightMenuVisible: false,
      rightMenuLeft: 0,
      rightMenuTop: 0,
      userName: "",
      menu: [],
      timeString: "",
      deskTopAppList: [],
      deskTopMenu: [
        // {
        //   key: "desktop",
        //   title: "桌面",
        //   sub: [
        //     {
        //       key: "big_icon",
        //       title: "大图标",
        //     },
        //     {
        //       key: "big_icon",
        //       title: "小图标",
        //     },
        //     {
        //       isLine: true
        //     },
        //     {
        //       key: "align_left",
        //       title: "左侧排列",
        //     },
        //     {
        //       key: "align_right",
        //       title: "右侧排列",
        //     },
        //     {
        //       isLine: true
        //     },
        //     {
        //       key: "wall",
        //       title: "更换壁纸...",
        //     }
        //   ]
        // }
      ],
      isWidgetShow: false,
    };
  },
  watch: {
    volumn() {
      this.$store.commit("setVolumn", this.volumn);
      clearTimeout(this.volumnDelayTimer);
      this.volumnDelayTimer = setTimeout(() => {
        this.isVolumnShow = false;
      }, 3000);
    },
    "$store.state.volumn"() {
      console.log(this.$store.state.volumn);
    },
    "$store.state.nowApp"() {
      this.menu = this.$store.state.nowApp.menu;
    },
    "$store.state.launchpad"() {
      this.$emit("launchpad", this.$store.state.launchpad);
    },
  },
  created() {
    this.menu = this.deskTopMenu;
    this.userName = localStorage.getItem("user_name") || "";
    this.deskTopAppList = this.tool.getDeskTopApp();
    this.startTimer();
    this.$store.commit("getDockAppList");
  },
  methods: {
    /**
     * @description: 显示或隐藏日历
     */
    showOrHideCalendar() {
      this.isCalendarShow = !this.isCalendarShow;
    },
    /**
     * @description: 显示或隐藏音量操作
     */
    showOrHideVolumn() {
      this.isVolumnShow = !this.isVolumnShow;
      if (this.isVolumnShow) {
        clearTimeout(this.volumnDelayTimer);
        this.volumnDelayTimer = setTimeout(() => {
          this.isVolumnShow = false;
        }, 3000);
      }
    },
    /**
     * @description: 隐藏所有弹出的控制器
     */
    hideAllController() {
      this.isVolumnShow = false;
      this.rightMenuVisible = false;
      this.isCalendarShow = false;
    },
    /**
     * @description: 打开右键菜单
     */
    openMenu(e) {
      const menuMinWidth = 105;
      const offsetLeft = this.$el.getBoundingClientRect().left; // container margin left
      const offsetWidth = this.$el.offsetWidth; // container width
      const maxLeft = offsetWidth - menuMinWidth; // left boundary
      const left = e.clientX - offsetLeft; // margin right

      if (left > maxLeft) {
        this.rightMenuLeft = maxLeft;
      } else {
        this.rightMenuLeft = left;
      }

      this.rightMenuTop = e.clientY - 30;
      this.rightMenuVisible = true;
    },
    /**
     * @description: 打开时间计时器
     */
    startTimer() {
      setInterval(() => {
        this.timeString = this.tool.formatTime(new Date(), "MM-dd HH:mm");
      }, 1000);
    },
    /**
     * @description: 打开指定key的应用
     */
    openAppByKey(key) {
      this.$store.commit("openAppByKey", key);
    },
    /**
     * @description: 锁定屏幕
     */
    lockScreen() {
      this.$emit("lockScreen");
    },
    /**
     * @description: 关机
     */
    shutdown() {
      this.$emit("shutdown");
    },
    /**
     * @description: 注销登录
     */
    logout() {
      this.$emit("logout");
    },
    showOrHideWidget() {
      this.isWidgetShow = !this.isWidgetShow;
    },
  },
};
</script>
<style>
.top .el-dropdown {
  color: white !important;
  height: 100% !important;
}
.top .el-calendar-day {
  height: 30px !important;
}
.top .is-today {
  background: #4b9efb !important;
  color: white !important;
}
</style>
<style scoped lang="scss">
.desktop {
  display: flex;
  flex-direction: column;
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  color: white;
  overflow: hidden;
  text-shadow: 0px 2px 2px rgba(0, 0, 0, 0.1);
  .top {
    height: 28px;
    background-color: rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(20px);
    display: flex;
    flex-direction: row;
    font-size: 14px;
    align-items: center;
    justify-content: center;
    padding: 0px 5px;
    z-index: 100;
    .logo {
      height: 100%;
      align-items: center;
      justify-content: center;
      padding: 0px 15px;
      cursor: pointer;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      .iconfont {
        font-size: 16px;
        margin-top: -3px;
      }
      .el-select {
        position: absolute;
        opacity: 0;
      }
    }

    .logo:hover {
      background-color: rgba(255, 255, 255, 0.1);
    }
    .space {
      flex-grow: 1;
    }
    .menu {
      display: flex;
      flex-direction: row;
      font-size: 13px;
      height: 100%;
      font-weight: 500;
      .item {
        font-size: 13px;
        padding: 0px 15px;
        display: inline-block;
        flex-grow: 1;
        cursor: pointer;
        display: flex;
        height: 100%;
        align-items: center;
        justify-content: center;
      }
      .item:hover {
        background-color: rgba(255, 255, 255, 0.1);
      }
    }

    .status {
      display: flex;
      flex-direction: row;
      justify-content: center;
      align-items: center;
      height: 100%;

      .audio {
        cursor: pointer;
        padding: 0px 10px;
        height: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
        text-align: center;
        position: relative;
        .iconfont {
          font-size: 20px;
        }
        .el-slider {
          position: absolute;
          top: 40px;
          height: 80px;
        }
      }
      .audio:hover {
        background-color: rgba(255, 255, 255, 0.1);
      }
      .datetime {
        cursor: pointer;
        padding: 0px 10px;
        height: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
        text-align: center;
        position: relative;
        .el-calendar {
          color: #333;
          background: rgba(255, 255, 255, 0.98);
          position: fixed;
          top: 40px;
          right: 20px;
          width: 500px;
          border-radius: 10px;
        }
      }
      .datetime:hover {
        background-color: rgba(255, 255, 255, 0.1);
      }
      .notification {
        cursor: pointer;
        padding: 0px 10px;
        height: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
        text-align: center;
        .iconfont {
          font-size: 20px;
        }
        .notification:hover {
          background-color: rgba(255, 255, 255, 0.1);
        }
      }
    }
  }

  .body {
    flex-grow: 1;
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    position: relative;
    .desktop-app {
      position: absolute;
      right: 0;
      top: 0;
      bottom: 0;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      align-items: flex-end;
      padding: 20px;
      flex-wrap: wrap-reverse;
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
        width: 80px;
        .icon {
          border-radius: 10px;
          display: flex;
          justify-content: center;
          align-items: center;
          text-align: center;
        }
        .iconfont {
          font-size: 28px;
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
      .app-item:hover {
        border: 2px solid rgba(255, 255, 255, 0.5);
      }
    }

    .contextmenu {
      position: absolute;
      background: rgba(255, 255, 255, 0.9);
      border-radius: 5px;
      box-shadow: 0px 0px 10px rgb(0 0 0 / 30%);
      color: #333;
      font-size: 14px;
      text-align: left;
      width: 200px;
      overflow: hidden;
      padding: 2px 0px;
      text-shadow: none;
      z-index: 100;
      hr {
        border: none;
        border-top: 1px solid #ddd;
      }
      div {
        cursor: pointer;
        font-size: 13px !important;
        color: #333;
        border-radius: 5px;
        line-height: 2;
        padding: 0px 12px;
        display: flex;
        align-items: center;
        margin: 3px 5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      div:hover {
        background: #4b9efb;
        color: white;
        border-radius: 5px;
      }
    }
  }
  .footer {
    display: flex;
    z-index: 100;
  }
}
</style>
