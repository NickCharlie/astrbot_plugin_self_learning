/**
 * MacOSRoot - Root application component using Composition API (setup()).
 * Orchestrates the passwordless boot sequence: desktop is shown directly.
 * Manages visibility of Bg, Loading, Login, DeskTop, and LaunchPad sub-components.
 */
window.MacOSRoot = {
  setup() {
    var ref = Vue.ref;
    var onMounted = Vue.onMounted;

    var isBg = ref(true);
    var isLoading = ref(false);
    var isLogin = ref(false);
    var isDeskTop = ref(false);
    var isLaunchPad = ref(false);

    /**
     * Pack 分支 WebUI 免密访问，始终直接进入桌面。
     */
    var checkAuth = async function () {
      return true;
    };

    /**
     * Boot sequence:
     *  - Skip login and go straight to desktop.
     */
    var boot = async function () {
      await checkAuth();
      isBg.value = true;
      isLoading.value = false;
      isLogin.value = false;
      isDeskTop.value = true;
    };

    /**
     * Called when Loading component finishes its progress bar.
     * Hides loading, shows desktop.
     */
    var loaded = function () {
      isLoading.value = false;
      isBg.value = true;
      isLogin.value = false;
      isDeskTop.value = true;
    };

    /**
     * Called when Login component emits successful authentication.
     * Hides login, shows desktop.
     */
    var logined = function () {
      isLogin.value = false;
      isDeskTop.value = true;
    };

    /**
     * Lock screen is disabled in passwordless mode.
     */
    var lockScreen = function () {
      isLogin.value = false;
      isDeskTop.value = true;
    };

    /**
     * Logout is a no-op in passwordless mode; keep desktop visible.
     */
    var logout = async function () {
      try {
        await fetch("/api/logout", {
          method: "POST",
          credentials: "same-origin",
        });
      } catch (e) {
        // ignore network errors during logout
      }
      localStorage.removeItem("user_name");
      isDeskTop.value = true;
      isLaunchPad.value = false;
      isLogin.value = false;
    };

    /**
     * Shutdown - hide everything.
     */
    var shutdown = function () {
      localStorage.removeItem("user_name");
      isDeskTop.value = false;
      isLaunchPad.value = false;
      isLogin.value = false;
      isLoading.value = false;
      isBg.value = false;
    };

    /**
     * Toggle launchpad visibility.
     */
    var launchpad = function (show) {
      isLaunchPad.value = show;
    };

    onMounted(function () {
      boot();
    });

    return {
      isBg: isBg,
      isLoading: isLoading,
      isLogin: isLogin,
      isDeskTop: isDeskTop,
      isLaunchPad: isLaunchPad,
      boot: boot,
      loaded: loaded,
      logined: logined,
      lockScreen: lockScreen,
      logout: logout,
      shutdown: shutdown,
      launchpad: launchpad,
    };
  },
  template: `
    <div class="mac-os" @mousedown.self="boot" @contextmenu.prevent="">
      <transition name="fade">
        <MacOSBg v-if="isBg"></MacOSBg>
      </transition>
      <transition name="fade">
        <MacOSLoading v-if="isLoading" @loaded="loaded"></MacOSLoading>
      </transition>
      <transition name="fade">
        <MacOSLogin v-if="isLogin" @logined="logined"></MacOSLogin>
      </transition>
      <transition name="fade">
        <MacOSDeskTop
          v-if="isDeskTop"
          @lockScreen="lockScreen"
          @shutdown="shutdown"
          @logout="logout"
          @launchpad="launchpad"
        ></MacOSDeskTop>
      </transition>
      <transition name="fade">
        <MacOSLaunchPad v-if="isLaunchPad"></MacOSLaunchPad>
      </transition>
    </div>
  `,
};
