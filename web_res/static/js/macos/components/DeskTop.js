/**
 * MacOSDeskTop - Main desktop component.
 * Renders the menu bar, desktop icons, open app windows, context menu, widgets, and dock.
 * Uses globally registered MacOSAppWindow, MacOSDock, MacOSWidget components.
 */
window.MacOSDeskTop = {
  template: `
    <div class="macos-desktop">
      <div class="top">
        <el-dropdown trigger="click">
          <div class="logo">
            <i class="iconfont icon-apple1"></i>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="openAppByKey('system_about')">
                <div>关于自学习插件</div>
              </el-dropdown-item>
              <el-dropdown-item class="line"></el-dropdown-item>
              <el-dropdown-item @click="openAppByKey('system_setting')">
                <div>系统偏好设置</div>
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
        @contextmenu.prevent.self="hideAllController(); openMenu($event);"
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
            <MacOSAppWindow
              v-if="!item.outLink"
              v-show="!item.hide"
              :app="item"
              :key="item.pid"
            ></MacOSAppWindow>
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
            <div @click="openAppByKey('system_about')">关于自学习插件</div>
          </div>
        </transition>
        <transition-group name="fade-widget">
          <div v-show="isWidgetShow">
            <template v-for="item in $store.state.openWidgetList" :key="item.pid">
              <MacOSWidget
                v-if="!item.outLink"
                v-show="!item.hide"
                :app="item"
                :key="item.pid"
              ></MacOSWidget>
            </template>
          </div>
        </transition-group>
      </div>
      <MacOSDock></MacOSDock>
    </div>
  `,
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
      userName: '',
      menu: [],
      timeString: '',
      deskTopAppList: [],
      deskTopMenu: [],
      isWidgetShow: false
    };
  },
  watch: {
    volumn() {
      this.$store.commit('setVolumn', this.volumn);
      clearTimeout(this.volumnDelayTimer);
      this.volumnDelayTimer = setTimeout(() => {
        this.isVolumnShow = false;
      }, 3000);
    },
    '$store.state.volumn'() {
      // sync volume from store if changed externally
    },
    '$store.state.nowApp'() {
      if (this.$store.state.nowApp && this.$store.state.nowApp.menu) {
        this.menu = this.$store.state.nowApp.menu;
      } else {
        this.menu = this.deskTopMenu;
      }
    },
    '$store.state.launchpad'() {
      this.$emit('launchpad', this.$store.state.launchpad);
    }
  },
  created() {
    this.menu = this.deskTopMenu;
    this.userName = localStorage.getItem('user_name') || '';
    this.deskTopAppList = window.MacOSTool.getDeskTopApp();
    this.startTimer();
    this.$store.commit('getDockAppList');
  },
  methods: {
    showOrHideCalendar() {
      this.isCalendarShow = !this.isCalendarShow;
    },
    showOrHideVolumn() {
      this.isVolumnShow = !this.isVolumnShow;
      if (this.isVolumnShow) {
        clearTimeout(this.volumnDelayTimer);
        this.volumnDelayTimer = setTimeout(() => {
          this.isVolumnShow = false;
        }, 3000);
      }
    },
    hideAllController() {
      this.isVolumnShow = false;
      this.rightMenuVisible = false;
      this.isCalendarShow = false;
    },
    openMenu(e) {
      var menuMinWidth = 105;
      var offsetLeft = this.$el.getBoundingClientRect().left;
      var offsetWidth = this.$el.offsetWidth;
      var maxLeft = offsetWidth - menuMinWidth;
      var left = e.clientX - offsetLeft;

      if (left > maxLeft) {
        this.rightMenuLeft = maxLeft;
      } else {
        this.rightMenuLeft = left;
      }

      this.rightMenuTop = e.clientY - 30;
      this.rightMenuVisible = true;
    },
    startTimer() {
      setInterval(() => {
        this.timeString = window.MacOSTool.formatTime(new Date(), 'MM-dd HH:mm');
      }, 1000);
    },
    openAppByKey(key) {
      this.$store.commit('openAppByKey', key);
    },
    lockScreen() {
      this.$emit('lockScreen');
    },
    shutdown() {
      this.$emit('shutdown');
    },
    logout() {
      this.$emit('logout');
    },
    showOrHideWidget() {
      this.isWidgetShow = !this.isWidgetShow;
    }
  }
};
