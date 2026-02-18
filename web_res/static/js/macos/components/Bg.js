/**
 * MacOSBg - Background wallpaper component
 * Renders a full-screen background image with optional blur filter.
 * Listens for wallpaper-change events and persists to localStorage.
 */
window.MacOSBg = {
  props: ["blur"],
  data() {
    return {
      wallpaper:
        localStorage.getItem("macos-wallpaper") || "/static/img/bg.jpg",
    };
  },
  mounted() {
    this._onWallpaperChange = (url) => {
      this.wallpaper = url;
    };
    window.EventBus.on("wallpaper-change", this._onWallpaperChange);
  },
  beforeUnmount() {
    window.EventBus.off("wallpaper-change", this._onWallpaperChange);
  },
  template: `<div class="macos-bg" :style="{ filter: 'blur(' + (blur || 0) + 'px)', backgroundImage: 'url(' + wallpaper + ')' }"></div>`,
};
