/**
 * 简易事件总线 - 替代 vue3-eventbus
 */
window.EventBus = {
  _events: {},
  emit(event, ...args) {
    (this._events[event] || []).forEach(fn => fn(...args));
  },
  on(event, fn) {
    (this._events[event] = this._events[event] || []).push(fn);
  },
  off(event, fn) {
    if (!fn) { delete this._events[event]; return; }
    this._events[event] = (this._events[event] || []).filter(f => f !== fn);
  }
};
