/**
 * MacOSAppWindow - Window frame component for each application.
 * Provides:
 *  - Drag via title bar (mousedown/mousemove/mouseup)
 *  - 8-point resize (box-top-left, box-top-center, box-top-right,
 *    box-center-left, box-center-right, box-bottom-left, box-bottom-center, box-bottom-right)
 *  - Title bar with close/min/max buttons
 *  - Dynamic component rendering via :is
 *  - z-index stacking (isTop)
 *  - Full screen and maximize toggle
 *  - appEvent handler for child app communication
 */
window.MacOSAppWindow = {
  props: {
    app: Object
  },
  template: `
    <div
      class="macos-movebg"
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
  `,
  watch: {
    app() {
      this.appData = Object.assign({ title: this.appData.title }, this.app);
    }
  },
  data() {
    return {
      appData: {
        title: ''
      },
      defaultIndex: 10,
      activeIndex: 20,
      isBoxMoving: false,
      startPosition: { x: 0, y: 0 },
      nowRect: {
        left: 100,
        right: 100,
        top: 100,
        bottom: 100
      },
      startRect: {
        left: 0,
        right: 0,
        top: 0,
        bottom: 0
      },
      isBoxResizing: false,
      moveDirection: false,
      isMaxShowing: false,
      isFullScreen: false
    };
  },
  created() {
    this.appData = Object.assign({}, this.app);
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
        this.nowRect.top =
          (document.body.clientHeight - this.app.height) / 2;
      }
    },
    /**
     * Listen for events emitted by child app components and handle or forward them.
     */
    appEvent(e) {
      switch (e.event) {
        case 'windowMaxSize':
          if (this.app.disableResize) return;
          this.isMaxShowing = true;
          this.isFullScreen = false;
          break;
        case 'windowNormalSize':
          if (this.app.disableResize) return;
          this.isMaxShowing = false;
          this.isFullScreen = false;
          break;
        case 'windowFullSize':
          if (this.app.disableResize) return;
          this.isFullScreen = true;
          this.isMaxShowing = true;
          break;
        case 'windowMinSize':
          this.hideApp();
          break;
        case 'windowClose':
          this.closeApp();
          break;
        case 'openApp':
          if (e.data && e.app) {
            this.$store.commit('openWithData', {
              app: window.MacOSTool.getAppByKey(e.app),
              data: e.data
            });
          } else {
            this.$store.commit('openApp', window.MacOSTool.getAppByKey(e.app));
          }
          break;
        case 'closeApp':
          if (e.pid) {
            this.$store.commit('closeWithPid', e.pid);
          }
          if (e.app) {
            this.$store.commit('closeApp', window.MacOSTool.getAppByKey(e.app));
          }
          break;
        case 'setWindowTitle':
          this.appData.title = e.title || this.app.title;
          break;
        default:
      }
    },
    closeApp() {
      this.$store.commit('closeApp', this.app);
    },
    hideApp() {
      this.$store.commit('hideApp', this.app);
    },
    showThisApp() {
      this.$store.commit('showApp', this.app);
    },
    switchFullScreen() {
      if (this.app.disableResize) return;
      this.isFullScreen = !this.isFullScreen;
      if (this.isFullScreen) {
        this.isMaxShowing = true;
      } else {
        this.isMaxShowing = false;
      }
    },
    getExtBoxClasses() {
      var str = '';
      if (!this.isBoxResizing && !this.isBoxMoving) {
        str += 'box-animation ';
      }
      if (this.isMaxShowing) {
        str += 'isMaxShowing ';
      }
      if (this.isFullScreen) {
        str += 'isFullScreen ';
      }
      if (this.app.disableResize) {
        str += 'resize-disabled ';
      }
      if (
        this.$store.state.openAppList.length > 0 &&
        this.$store.state.openAppList[this.$store.state.openAppList.length - 1].pid === this.app.pid
      ) {
        str += 'isTop ';
      }
      return str;
    },
    appBarDoubleClicked() {
      if (this.app.disableResize) return;
      this.isMaxShowing = !this.isMaxShowing;
      if (!this.isMaxShowing) {
        this.isFullScreen = false;
      }
    },
    positionMouseDown(e) {
      this.showThisApp();
      if (this.isFullScreen || this.isMaxShowing) return;
      this.startRect = {
        left: this.nowRect.left,
        right: this.nowRect.right,
        top: this.nowRect.top,
        bottom: this.nowRect.bottom
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
          case 'box-top-left':
            this.nowRect.top =
              this.startRect.top + (e.clientY - this.startPosition.y);
            this.nowRect.left =
              this.startRect.left + (e.clientX - this.startPosition.x);
            break;
          case 'box-top-center':
            this.nowRect.top =
              this.startRect.top + (e.clientY - this.startPosition.y);
            break;
          case 'box-top-right':
            this.nowRect.top =
              this.startRect.top + (e.clientY - this.startPosition.y);
            this.nowRect.right =
              this.startRect.right - (e.clientX - this.startPosition.x);
            break;
          case 'box-center-left':
            this.nowRect.left =
              this.startRect.left + (e.clientX - this.startPosition.x);
            break;
          case 'box-bottom-left':
            this.nowRect.left =
              this.startRect.left + (e.clientX - this.startPosition.x);
            this.nowRect.bottom =
              this.startRect.bottom - (e.clientY - this.startPosition.y);
            break;
          case 'box-bottom-center':
            this.nowRect.bottom =
              this.startRect.bottom - (e.clientY - this.startPosition.y);
            break;
          case 'box-center-right':
            this.nowRect.right =
              this.startRect.right - (e.clientX - this.startPosition.x);
            break;
          case 'box-bottom-right':
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
      if (this.app.disableResize) return;
      this.showThisApp();
      if (this.isFullScreen || this.isMaxShowing) return;
      this.startRect = {
        left: this.nowRect.left,
        top: this.nowRect.top,
        right: this.nowRect.right,
        bottom: this.nowRect.bottom
      };
      this.startPosition.x = e.clientX;
      this.startPosition.y = e.clientY;
      this.isBoxResizing = true;
      this.moveDirection = e.target.className;
    }
  }
};
