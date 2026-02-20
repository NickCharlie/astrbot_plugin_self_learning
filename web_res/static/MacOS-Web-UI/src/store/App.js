import AppModel from "@/model/App";
import tool from "@/helper/tool";
import bus from 'vue3-eventbus'
export default {
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
    /**
     * @description: 设置全局音量
     */
    setVolumn(state, volumn) {
      state.volumn = volumn;
    },
    /**
     * @description: 退出登录
     */
    logout(state) {
      state.nowApp = false;
      state.openAppList = [];
      state.showLogin = true;
    },
    /**
     * @description: 登录
     */
    login(state) {
      state.showLogin = false;
    },
    /**
     * @description: 打开上一次的应用
     */
    openTheLastApp(state) {
      for (let i = state.openAppList.length - 1; i >= 0; i--) {
        if (!state.openAppList[i].hide) {
          this.commit("showApp", state.openAppList[i]);
          break;
        }
      }
    },
    /**
     * @description: 最小化应用
     */
    hideApp(state, app) {
      for (let i in state.openAppList) {
        if (state.openAppList[i].pid == app.pid) {
          state.openAppList[i].hide = true;
          break;
        }
      }
      this.commit("openTheLastApp");
    },
    /**
     * @description: 根据PID关闭应用
     */
    closeWithPid(state, pid) {
      for (let i in state.openAppList) {
        if (state.openAppList[i].pid == pid) {
          state.openAppList.splice(i, 1);
          break;
        }
      }
      for (let i in state.dockAppList) {
        if (
          state.dockAppList[i].pid == pid &&
          !state.dockAppList[i].keepInDock
        ) {
          state.dockAppList.splice(i, 1);
          break;
        }
      }
    },
    /**
     * @description: 关闭应用
     */
    closeApp(state, app) {
      if (app.hideWhenClose) {
        this.commit("hideApp", app);
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
        this.commit("openTheLastApp");
      }
    },
    /**
     * @description: 打开应用
     */
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
        this.commit("showApp", app);
      } else {
        app.pid =
          new Date().valueOf() + "." + parseInt(Math.random() * 99999999);
        app = JSON.parse(JSON.stringify(app));
        state.openAppList.push(app);
        let isExistDock = false;
        for (let i in state.dockAppList) {
          if (state.dockAppList[i].key == app.key) {
            //dock里已经有相同的应用了 不push
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
    /**
     * @description: 显示并置顶APP
     */
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
    /**
     * @description: 根据key打开APP
     */
    openAppByKey(state, key) {
      let app = tool.getAppByKey(key);
      if (app) {
        this.commit("openApp", app);
      }
    },
    /**
     * @description: 带参数打开App
     */
    openWithData(state, data) {
      data.app.data = data.data;
      this.commit("openApp", data.app);
    },
    /**
     * @description: 获取常驻Dock的App列表
     */
    getDockAppList(state) {
      let arr = [];
      let appList = AppModel.allAppList;
      for (let app of appList) {
        if (app.keepInDock) {
          app.pid =
            new Date().valueOf() + "." + parseInt(Math.random() * 99999999);
          arr.push(app);
        }
      }
      state.dockAppList = arr;
    },
    openMenu(state, key) {
      switch (key) {
        case "close":
          this.commit("closeApp", state.nowApp);
          break;
        default:          
          bus.emit(key);  //默认通过事件总线发送，注意保证事件名称唯一
          break;
      }
    },
    launchpad(state) {
      state.launchpad = !state.launchpad;
    },
  },
};
