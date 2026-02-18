/**
 * Vuex Store - 窗口管理状态
 * 移植自 MacOS-Web-UI/src/store/App.js
 */
window.MacOSStoreConfig = {
  state() {
    return {
      showLogin: false,
      nowApp: false,
      openAppList: [],
      dockAppList: [],
      openWidgetList: [],
      volumn: 80,
      launchpad: false,
    };
  },
  mutations: {
    setVolumn(state, volumn) {
      state.volumn = volumn;
    },
    logout(state) {
      state.nowApp = false;
      state.openAppList = [];
      state.showLogin = true;
    },
    login(state) {
      state.showLogin = false;
    },
    openTheLastApp(state) {
      for (let i = state.openAppList.length - 1; i >= 0; i--) {
        if (!state.openAppList[i].hide) {
          this.commit('showApp', state.openAppList[i]);
          break;
        }
      }
    },
    hideApp(state, app) {
      for (let i in state.openAppList) {
        if (state.openAppList[i].pid == app.pid) {
          state.openAppList[i].hide = true;
          break;
        }
      }
      this.commit('openTheLastApp');
    },
    closeWithPid(state, pid) {
      for (let i in state.openAppList) {
        if (state.openAppList[i].pid == pid) {
          state.openAppList.splice(i, 1);
          break;
        }
      }
      for (let i in state.dockAppList) {
        if (state.dockAppList[i].pid == pid && !state.dockAppList[i].keepInDock) {
          state.dockAppList.splice(i, 1);
          break;
        }
      }
    },
    closeApp(state, app) {
      if (app.hideWhenClose) {
        this.commit('hideApp', app);
      } else {
        for (let i in state.openAppList) {
          if (app.pid) {
            if (state.openAppList[i].pid == app.pid) {
              state.openAppList.splice(i, 1);
              break;
            }
          } else {
            if (state.openAppList[i].key == app.key) {
              state.openAppList.splice(i, 1);
              break;
            }
          }
        }
        if (!app.keepInDock) {
          for (let i in state.dockAppList) {
            if (app.pid) {
              if (state.dockAppList[i].pid == app.pid) {
                state.dockAppList.splice(i, 1);
                break;
              }
            } else {
              if (state.dockAppList[i].key == app.key) {
                state.dockAppList.splice(i, 1);
                break;
              }
            }
          }
        }
        this.commit('openTheLastApp');
      }
    },
    openApp(state, app) {
      if (state.launchpad) {
        state.launchpad = false;
      }
      if (app.outLink) {
        app.url && window.open(app.url);
        return;
      }
      app.hide = false;
      let isExist = false;
      for (let i in state.openAppList) {
        if (state.openAppList[i].key == app.key) {
          isExist = true;
          break;
        }
      }
      if (isExist) {
        this.commit('showApp', app);
      } else {
        app.pid = new Date().valueOf() + '.' + parseInt(Math.random() * 99999999);
        app = JSON.parse(JSON.stringify(app));
        state.openAppList.push(app);
        let isExistDock = false;
        for (let i in state.dockAppList) {
          if (state.dockAppList[i].key == app.key) {
            isExistDock = true;
            break;
          }
        }
        if (!isExistDock) {
          state.dockAppList.push(app);
        }
      }
      state.nowApp = JSON.parse(JSON.stringify(app));
    },
    showApp(state, app) {
      let openAppList = JSON.parse(JSON.stringify(state.openAppList));
      for (let i in openAppList) {
        if (openAppList[i].pid == app.pid) {
          openAppList.splice(i, 1);
          break;
        }
      }
      app.hide = false;
      app = JSON.parse(JSON.stringify(app));
      openAppList.push(app);
      state.openAppList = openAppList;
      state.nowApp = app;
    },
    openAppByKey(state, key) {
      let app = window.MacOSTool.getAppByKey(key);
      if (app) {
        this.commit('openApp', app);
      }
    },
    openWithData(state, data) {
      data.app.data = data.data;
      this.commit('openApp', data.app);
    },
    getDockAppList(state) {
      let arr = [];
      let appList = window.AppModel.allAppList;
      for (let app of appList) {
        if (app.keepInDock) {
          app.pid = new Date().valueOf() + '.' + parseInt(Math.random() * 99999999);
          arr.push(app);
        }
      }
      state.dockAppList = arr;
    },
    openMenu(state, key) {
      switch (key) {
        case 'close':
          this.commit('closeApp', state.nowApp);
          break;
        default:
          window.EventBus.emit(key);
          break;
      }
    },
    launchpad(state) {
      state.launchpad = !state.launchpad;
    },
  },
};
