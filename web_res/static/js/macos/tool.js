/**
 * 工具函数 - 移植自 MacOS-Web-UI/src/helper/tool.js
 */
window.MacOSTool = {
  getAccessToken() {
    return localStorage.getItem('AcessToken') || '';
  },
  saveAccessToken(access_token) {
    localStorage.setItem('AcessToken', access_token);
  },
  isAppInKeepList(app, dockAppList) {
    for (let item of dockAppList) {
      if (item.key === app.key) return true;
    }
    return false;
  },
  isAppInOpenList(app, openAppList) {
    for (let item of openAppList) {
      if (item.key === app.key) return true;
    }
    return false;
  },
  getAppByKey(key) {
    let appList = window.AppModel.allAppList;
    for (let app of appList) {
      if (app.key === key) return app;
    }
    return false;
  },
  getDeskTopApp() {
    return window.AppModel.allAppList;
  },
  formatTime(date, format) {
    if (!date) return;
    if (!format) format = 'yyyy-MM-dd';
    switch (typeof date) {
      case 'string':
        date = new Date(date.replace(/-/, '/'));
        break;
      case 'number':
        date = new Date(date);
        break;
      default:
    }
    var dict = {
      'yyyy': date.getFullYear(),
      'M': date.getMonth() + 1,
      'd': date.getDate(),
      'H': date.getHours(),
      'm': date.getMinutes(),
      's': date.getSeconds(),
      'MM': ('' + (date.getMonth() + 101)).substr(1),
      'dd': ('' + (date.getDate() + 100)).substr(1),
      'HH': ('' + (date.getHours() + 100)).substr(1),
      'mm': ('' + (date.getMinutes() + 100)).substr(1),
      'ss': ('' + (date.getSeconds() + 100)).substr(1),
    };
    return format.replace(/(yyyy|MM?|dd?|HH?|ss?|mm?)/g, function () {
      return dict[arguments[0]];
    });
  }
};
