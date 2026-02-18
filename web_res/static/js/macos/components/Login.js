/**
 * MacOSLogin - Password-only login screen customized for backend auth.
 * Features:
 *  - Avatar circle with title "自学习管理后台"
 *  - Password input + submit button
 *  - POST /api/login with {password} via fetch
 *  - 401 error shake animation
 *  - 429 rate-limit countdown
 *  - must_change redirect to /api/plugin_change_password
 *  - Enter key submission
 */
window.MacOSLogin = {
  template: `
    <div class="macos-login">
      <div class="head"><img src="/static/img/logo.png" alt="Logo" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" /></div>
      <div class="message">自学习管理后台</div>
      <div class="form">
        <div class="item" :class="isError ? 'error' : ''">
          <input
            class="password"
            :placeholder="placeholderText"
            type="password"
            v-model="password"
            :class="password ? 'password-in' : ''"
            @keyup.enter="login"
            :disabled="isLocked"
            ref="passwordInput"
          />
          <i
            class="login-button iconfont icon-icon_send"
            :class="password && !isLocked ? 'click-enable' : ''"
            @click="login"
          ></i>
        </div>
        <div class="error-message" v-if="errorMsg">{{ errorMsg }}</div>
      </div>
    </div>
  `,
  data() {
    return {
      password: "",
      isError: false,
      errorMsg: "",
      isLocked: false,
      lockCountdown: 0,
      lockTimer: null,
      placeholderText: "请输入密码...",
    };
  },
  mounted() {
    this.$nextTick(() => {
      if (this.$refs.passwordInput) {
        this.$refs.passwordInput.focus();
      }
    });
  },
  beforeUnmount() {
    if (this.lockTimer) {
      clearInterval(this.lockTimer);
      this.lockTimer = null;
    }
  },
  methods: {
    async login() {
      if (this.isLocked) return;
      if (!this.password) {
        this.shakeError("请输入密码");
        return;
      }

      try {
        var resp = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ password: this.password }),
        });

        if (resp.ok) {
          var data = await resp.json();
          if (data && data.must_change) {
            window.location.href = "/api/plugin_change_password";
            return;
          }
          var userName = data && data.user_name ? data.user_name : "Admin";
          localStorage.setItem("user_name", userName);
          this.errorMsg = "";
          this.password = "";
          this.$emit("logined");
        } else if (resp.status === 401) {
          this.shakeError("密码错误，请重试");
          this.password = "";
        } else if (resp.status === 429) {
          var retryData = null;
          try {
            retryData = await resp.json();
          } catch (e) {
            /* ignore */
          }
          var waitSeconds =
            retryData && retryData.retry_after ? retryData.retry_after : 30;
          this.startLockCountdown(waitSeconds);
        } else {
          this.shakeError("登录失败 (" + resp.status + ")");
        }
      } catch (err) {
        this.shakeError("网络错误，请检查连接");
      }
    },
    shakeError(msg) {
      this.errorMsg = msg;
      this.isError = true;
      setTimeout(() => {
        this.isError = false;
      }, 1000);
    },
    startLockCountdown(seconds) {
      this.isLocked = true;
      this.lockCountdown = seconds;
      this.errorMsg = "登录过于频繁，请等待 " + this.lockCountdown + " 秒";
      this.password = "";

      if (this.lockTimer) clearInterval(this.lockTimer);
      this.lockTimer = setInterval(() => {
        this.lockCountdown--;
        if (this.lockCountdown <= 0) {
          clearInterval(this.lockTimer);
          this.lockTimer = null;
          this.isLocked = false;
          this.errorMsg = "";
          this.placeholderText = "请输入密码...";
        } else {
          this.errorMsg = "登录过于频繁，请等待 " + this.lockCountdown + " 秒";
        }
      }, 1000);
    },
  },
};
