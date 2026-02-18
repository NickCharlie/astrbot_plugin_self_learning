/**
 * MacOSLoading - Boot screen with Apple logo and animated progress bar.
 * Emits 'loaded' when the progress bar finishes.
 */
window.MacOSLoading = {
  template: `
    <div class="macos-loading" @click="fullScreen">
      <div class="logo"><img src="/static/img/logo.png" alt="Logo" style="width:120px;height:120px;object-fit:contain;border-radius:50%;" /></div>
      <div class="progress" :style="{ width: showProgress ? '300px' : '0px' }">
        <div :style="{ width: progress + '%' }"></div>
      </div>
    </div>
  `,
  data() {
    return {
      progress: 0,
      showProgress: false,
    };
  },
  created() {
    setTimeout(() => {
      this.showProgress = true;
      this.updateProgress();
    }, 1000);
  },
  methods: {
    fullScreen() {
      var docElm = document.documentElement;
      if (docElm.requestFullscreen) {
        docElm.requestFullscreen();
      } else if (docElm.msRequestFullscreen) {
        docElm.msRequestFullscreen();
      } else if (docElm.mozRequestFullScreen) {
        docElm.mozRequestFullScreen();
      } else if (docElm.webkitRequestFullScreen) {
        docElm.webkitRequestFullScreen();
      }
    },
    updateProgress() {
      this.progress += parseInt(Math.random() * 2);
      if (this.progress >= 100) {
        this.progress = 100;
        this.showProgress = false;
        setTimeout(() => this.$emit("loaded"), 1000);
      } else {
        requestAnimationFrame(this.updateProgress);
      }
    },
  },
};
