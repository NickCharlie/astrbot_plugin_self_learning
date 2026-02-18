/**
 * MacOSRoot - Root application component using Composition API (setup()).
 * Orchestrates the boot sequence: loading -> login -> desktop.
 * Auth check via GET /api/config to skip loading if already authenticated.
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
     * Check if user is already authenticated by probing /api/config.
     * Returns true if authenticated (non-401), false otherwise.
     */
    var checkAuth = async function () {
      try {
        var resp = await fetch("/api/config", { credentials: "same-origin" });
        return resp.status !== 401;
      } catch (e) {
        return false;
      }
    };

    /**
     * Boot sequence:
     *  - If already authenticated, skip loading animation and go straight to desktop.
     *  - Otherwise, show loading screen which will emit 'loaded' when done.
     */
    var boot = async function () {
      var authed = await checkAuth();
      if (authed) {
        // Already authenticated - go straight to desktop
        isBg.value = true;
        isLoading.value = false;
        isLogin.value = false;
        isDeskTop.value = true;
      } else {
        // Not authenticated - go straight to login (no loading animation)
        isBg.value = true;
        isLoading.value = false;
        isLogin.value = true;
      }
    };

    /**
     * Called when Loading component finishes its progress bar.
     * Hides loading, shows login.
     */
    var loaded = function () {
      isLoading.value = false;
      isBg.value = true;
      isLogin.value = true;
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
     * Lock screen - show login overlay on top of desktop.
     */
    var lockScreen = function () {
      isLogin.value = true;
    };

    /**
     * Logout - POST /api/logout, then hide desktop and show login.
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
      isDeskTop.value = false;
      isLaunchPad.value = false;
      isLogin.value = true;
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
