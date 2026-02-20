<template>
  <div
    class="moveBg"
    @mousemove="mouseMove"
    @mouseup="mouseUp"
    @mouseleave.stop="mouseLeave"
    :style="{
      pointerEvents: isBoxResizing || isBoxMoving ? 'auto' : 'none',
      zIndex: isFullScreen ? 999 : app.isTop ? 98 : 88,
    }"
  >
    <div
      class="box"
      :style="{
        left: nowRect.left + 'px',
        top: nowRect.top + 'px',
        bottom: nowRect.bottom + 'px',
        right: nowRect.right + 'px',
      }"
      :class="getExtBoxClasses()"
    >
      <div class="box-top">
        <div class="box-top-left" @mousedown="resizeMouseDown"></div>
        <div class="box-top-center" @mousedown="resizeMouseDown"></div>
        <div class="box-top-right" @mousedown="resizeMouseDown"></div>
      </div>
      <div class="box-center">
        <div class="box-center-left" @mousedown="resizeMouseDown"></div>
        <div class="box-center-center loader" @mousedown.stop="showThisApp">
          <div
            class="app-bar"
            :style="{ backgroundColor: app.titleBgColor }"
            @mousedown.stop="positionMouseDown"
            v-on:dblclick="appBarDoubleClicked"
          >
            <div class="controll">
              <div class="close" @click.stop="closeApp"></div>
              <div class="min" @click.stop="hideApp"></div>
              <div
                class="full"
                :class="app.disableResize ? 'full-disabled' : ''"
                @click="switchFullScreen"
              ></div>
            </div>
            <div class="title" :style="{ color: app.titleColor }">
              {{ appData.title || app.title }}
            </div>
          </div>
          <div class="app-body">
            <component
              :is="app.component"
              :app="app"
              @api="appEvent"
            ></component>
          </div>
        </div>
        <div class="box-center-right" @mousedown="resizeMouseDown"></div>
      </div>
      <div class="box-bottom">
        <div class="box-bottom-left" @mousedown="resizeMouseDown"></div>
        <div class="box-bottom-center" @mousedown="resizeMouseDown"></div>
        <div class="box-bottom-right" @mousedown="resizeMouseDown"></div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineAsyncComponent } from "vue";
export default {
  components: {
    SystemAbout: defineAsyncComponent(() => import("@/view/system/about")),
    SystemFinder: defineAsyncComponent(() => import("@/view/system/finder")),
    SystemSetting: defineAsyncComponent(() => import("@/view/system/setting")),
    SystemStore: defineAsyncComponent(() => import("@/view/system/store")),
    SystemTask: defineAsyncComponent(() => import("@/view/system/task")),
    Demo: defineAsyncComponent(() => import("@/view/demo/demo")),
    DemoDock: defineAsyncComponent(() => import("@/view/demo/dock")),
    DemoUnResize: defineAsyncComponent(() => import("@/view/demo/unresize")),
    DemoUnClose: defineAsyncComponent(() => import("@/view/demo/unclose")),
    DemoHideDesktop: defineAsyncComponent(() =>
      import("@/view/demo/hidedesktop")
    ),
    DemoColorFull: defineAsyncComponent(() => import("@/view/demo/colorfull")),
    DemoCamera: defineAsyncComponent(() => import("@/view/demo/camera")),
    DemoMultiTask: defineAsyncComponent(() => import("@/view/demo/multitask")),
    DemoWeb: defineAsyncComponent(() => import("@/view/demo/web")),
  },
  props: {
    app: Object,
  },
  watch: {
    app() {
      this.appData = Object({ title: this.appData.title }, this.app);
    },
  },
  data() {
    return {
      appData: {
        title: "",
      },
      defaultIndex: 10,
      activeIndex: 20,
      isBoxMoving: false,
      startPosition: { x: 0, y: 0 },
      nowRect: {
        left: 100,
        right: 100,
        top: 100,
        bottom: 100,
      },
      startRect: {
        left: 0,
        right: 0,
        top: 0,
        bottom: 0,
      },
      isBoxResizing: false,
      moveDirection: false,
      isMaxShowing: false,
      isFullScreen: false,
    };
  },
  created() {
    this.appData = Object({}, this.app);
    this.setReact();
  },
  methods: {
    setReact() {
      if (this.app.width) {
        this.nowRect.left = this.nowRect.right =
          (document.body.clientWidth - this.app.width) / 2;
      }
      if (this.app.height) {
        this.nowRect.bottom =
          (document.body.clientHeight - this.app.height) / 2;
        this.nowRect.top = (document.body.clientHeight - this.app.height) / 2;
      }
    },
    /**
     * @description: 监听APP发送的事件 转发或处理到桌面组件中
     */
    appEvent(e) {
      switch (e.event) {
        case "windowMaxSize":
          if (this.app.disableResize) {
            return;
          }
          this.isMaxShowing = true;
          this.isFullScreen = false;
          break;
        case "windowNormalSize":
          if (this.app.disableResize) {
            return;
          }
          this.isMaxShowing = false;
          this.isFullScreen = false;
          break;
        case "windowFullSize":
          if (this.app.disableResize) {
            return;
          }
          this.isFullScreen = true;
          this.isMaxShowing = true;
          break;
        case "windowMinSize":
          this.hideApp();
          break;
        case "windowClose":
          this.closeApp();
          break;
        case "openApp":
          if (e.data && e.app) {
            this.$store.commit("openWithData", {
              app: this.tool.getAppByKey(e.app),
              data: e.data,
            });
          } else {
            this.$store.commit("openApp", this.tool.getAppByKey(e.app));
          }
          break;
        case "closeApp":
          if (e.pid) {
            this.$store.commit("closeWithPid", e.pid);
          }
          if (e.app) {
            this.$store.commit("closeApp", this.tool.getAppByKey(e.app));
          }
          break;
        case "setWindowTitle":
          this.appData.title = e.title || this.app.title;
          break;
        default:
      }
    },
    /**
     * @description: 关闭当前应用
     */
    closeApp() {
      this.$store.commit("closeApp", this.app);
    },
    /**
     * @description: 隐藏当前应用
     */
    hideApp() {
      this.$store.commit("hideApp", this.app);
    },
    showThisApp() {
      this.$store.commit("showApp", this.app);
    },
    /**
     * @description: 全屏切换
     */
    switchFullScreen() {
      if (this.app.disableResize) {
        return;
      }
      this.isFullScreen = !this.isFullScreen;
      if (this.isFullScreen) {
        this.isMaxShowing = true;
      } else {
        this.isMaxShowing = false;
      }
    },
    /**
     * @description: 返回应用配置的样式类
     */
    getExtBoxClasses() {
      let str = "";
      if (!this.isBoxResizing && !this.isBoxMoving) {
        str += "box-animation ";
      }
      if (this.isMaxShowing) {
        str += "isMaxShowing ";
      }
      if (this.isFullScreen) {
        str += "isFullScreen ";
      }
      if (this.app.disableResize) {
        str += "resize-disabled ";
      }
      if (
        this.$store.state.openAppList[this.$store.state.openAppList.length - 1]
          .pid == this.app.pid
      ) {
        str += "isTop ";
      }
      return str;
    },
    /**
     * @description: 标题栏被双击 缩放
     */
    appBarDoubleClicked() {
      if (this.app.disableResize) {
        return;
      }
      this.isMaxShowing = !this.isMaxShowing;
      if (!this.isMaxShowing) {
        this.isFullScreen = false;
      }
    },
    /**
     * @description: 鼠标按下
     */
    positionMouseDown(e) {
      // console.warn("positionMouseDown")
      this.showThisApp();
      if (this.isFullScreen || this.isMaxShowing) {
        return;
      }
      this.startRect = {
        left: this.nowRect.left,
        right: this.nowRect.right,
        top: this.nowRect.top,
        bottom: this.nowRect.bottom,
      };
      this.startPosition.x = e.clientX;
      this.startPosition.y = e.clientY;
      this.isBoxMoving = true;
    },
    mouseUp() {
      this.isBoxMoving = false;
      this.isBoxResizing = false;
      this.moveDirection = false;
    },
    mouseLeave() {
      this.isBoxMoving = false;
      this.isBoxResizing = false;
      this.moveDirection = false;
    },
    mouseMove(e) {
      if (this.isBoxResizing) {
        this.isFullScreen = false;
        this.isMaxShowing = false;
        switch (this.moveDirection) {
          case "box-top-left":
            this.nowRect.top =
              this.startRect.top + (e.clientY - this.startPosition.y);
            this.nowRect.left =
              this.startRect.left + (e.clientX - this.startPosition.x);
            break;
          case "box-top-center":
            this.nowRect.top =
              this.startRect.top + (e.clientY - this.startPosition.y);
            break;
          case "box-top-right":
            this.nowRect.top =
              this.startRect.top + (e.clientY - this.startPosition.y);
            this.nowRect.right =
              this.startRect.right - (e.clientX - this.startPosition.x);
            break;
          case "box-center-left":
            this.nowRect.left =
              this.startRect.left + (e.clientX - this.startPosition.x);
            break;
          case "box-bottom-left":
            this.nowRect.left =
              this.startRect.left + (e.clientX - this.startPosition.x);
            this.nowRect.bottom =
              this.startRect.bottom - (e.clientY - this.startPosition.y);
            break;
          case "box-bottom-center":
            this.nowRect.bottom =
              this.startRect.bottom - (e.clientY - this.startPosition.y);
            break;
          case "box-center-right":
            this.nowRect.right =
              this.startRect.right - (e.clientX - this.startPosition.x);
            break;
          case "box-bottom-right":
            this.nowRect.right =
              this.startRect.right - (e.clientX - this.startPosition.x);
            this.nowRect.bottom =
              this.startRect.bottom - (e.clientY - this.startPosition.y);
            break;
          default:
        }
        return;
      }
      if (this.isBoxMoving) {
        this.isFullScreen = false;
        this.isMaxShowing = false;
        this.nowRect.left =
          this.startRect.left + (e.clientX - this.startPosition.x);
        this.nowRect.right =
          this.startRect.right - (e.clientX - this.startPosition.x);
        this.nowRect.top =
          this.startRect.top + (e.clientY - this.startPosition.y);
        this.nowRect.bottom =
          this.startRect.bottom - (e.clientY - this.startPosition.y);
        return;
      }
    },
    resizeMouseDown(e) {
      if (this.app.disableResize) {
        return;
      }
      this.showThisApp();
      if (this.isFullScreen || this.isMaxShowing) {
        return;
      }
      this.startRect = {
        left: this.nowRect.left,
        top: this.nowRect.top,
        right: this.nowRect.right,
        bottom: this.nowRect.bottom,
      };
      this.startPosition.x = e.clientX;
      this.startPosition.y = e.clientY;
      this.isBoxResizing = true;
      this.moveDirection = e.target.className;
    },
  },
};
</script>
<style scoped lang="scss">
.moveBg {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  .isTop {
    .box-center-center {
      box-shadow: 0px 0px 20px rgba(0, 0, 0, 0.5) !important;
      filter: none !important;
    }
  }
  .isMaxShowing {
    left: -5px !important;
    right: -5px !important;
    top: 23px !important;
    bottom: 41px !important;
  }

  .isFullScreen {
    position: fixed !important;
    z-index: 999 !important;
    bottom: -5px !important;
    top: -5px !important;
  }

  .isMaxShowing .box-center-center,
  .isFullScreen .box-center-center {
    border-radius: 0px !important;
  }
  .box-animation {
    transition: width 0.1s, height 0.1s, left 0.1s, right 0.1s, top 0.1s,
      bottom 0.1s;
  }
  .resize-disabled {
    .box-top,
    .box-top-left,
    .box-top-center,
    .box-top-right,
    .box-left,
    .box-center-left,
    .box-center-right,
    .box-right,
    .box-bottom,
    .box-bottom-left,
    .box-bottom-center,
    .box-bottom-right {
      cursor: default !important;
    }
  }
  .box {
    --resize: 5px;
    --resize-bg: transparent;
    --resize-main: transparent;
    --resize-bg-main: transparent;
  }

  .box {
    display: flex;
    flex-direction: column;
    position: absolute;
    pointer-events: auto;

    .box-top {
      display: flex;
      flex-direction: row;
      .box-top-left {
        width: var(--resize);
        height: var(--resize);
        background: var(--resize-bg);
        cursor: nw-resize;
      }

      .box-top-center {
        height: var(--resize);
        background: var(--resize-bg-main);
        cursor: n-resize;
        flex-grow: 1;
      }

      .box-top-right {
        width: var(--resize);
        height: var(--resize);
        background: var(--resize-bg);
        cursor: ne-resize;
      }
    }

    .box-center {
      display: flex;
      flex-direction: row;
      flex-grow: 1;

      .loader {
        display: flex;
        flex-grow: 1;
        flex-direction: column;
        width: 100%;
      }
      .box-center-left {
        width: var(--resize);
        height: 100%;
        background: var(--resize-bg-main);
        cursor: w-resize;
      }

      .box-center-center {
        height: 100%;
        flex-grow: 1;
        display: flex;
        flex-direction: column;
        border-radius: 10px;
        box-shadow: 0px 0px 3px #999;
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(20px);
        overflow: hidden;
        filter: grayscale(1) brightness(0.9);
        .app-bar {
          height: 40px;
          background: rgba(255, 255, 255, 0.5);
          backdrop-filter: blur(20px);
          display: flex;
          flex-direction: row;
          justify-content: center;
          align-items: center;
          white-space: nowrap;
          text-overflow: ellipsis;
          overflow: hidden;
          .title {
            flex-grow: 1;
            text-align: center;
            margin-right: 84px;
            font-weight: 500;
            text-shadow: none;
            font-size: 13px;
            cursor: move;
            color: #333;
          }
          .controll {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-left: 15px;
            div {
              border-radius: 100%;
              height: 14px;
              width: 14px;
              margin-right: 8px;
              cursor: pointer;
            }
            .close {
              background: #fc605c;
            }
            .close:hover {
              background: #cc2c26;
            }
            .min {
              background: #fcbb40;
            }
            .min:hover {
              background: #c28719;
            }
            .full {
              background: #34c648;
            }
            .full:hover {
              background: #1f942e;
            }

            .full-disabled {
              background: #ccc !important;
            }
          }
        }

        .app-body {
          flex-grow: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          height: 0;
        }
      }
      .box-center-right {
        width: var(--resize);
        height: 100%;
        background: var(--resize-bg-main);
        cursor: e-resize;
      }
    }

    .box-bottom {
      display: flex;
      flex-direction: row;
      .box-bottom-left {
        width: var(--resize);
        height: var(--resize);
        background: var(--resize-bg);
        cursor: sw-resize;
      }

      .box-bottom-center {
        height: var(--resize);
        background: var(--resize-bg-main);
        cursor: s-resize;
        flex-grow: 1;
      }

      .box-bottom-right {
        width: var(--resize);
        height: var(--resize);
        background: var(--resize-bg);
        cursor: se-resize;
      }
    }
  }
}
</style>
