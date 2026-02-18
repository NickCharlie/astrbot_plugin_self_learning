/**
 * MacOSBg - Background wallpaper component
 * Renders a full-screen background image with optional blur filter.
 */
window.MacOSBg = {
  props: ['blur'],
  template: `<div class="macos-bg" :style="{ filter: 'blur(' + (blur || 0) + 'px)', backgroundImage: 'url(/static/img/bg.jpg)' }"></div>`
};
