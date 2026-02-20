import AppModel from "@/model/App"
export default {
    /**
     * @description: 从localstorage中获取access_token
     */
    getAccessToken() {
        return localStorage.getItem('AcessToken') || ""
    },
    /**
     * @description: 保存access_token到localstorage
     */
    saveAccessToken(access_token) {
        localStorage.setItem('AcessToken', access_token)
    },
    /**
     * @description: APP是否常驻Dock
     */
    isAppInKeepList(app, dockAppList) {
        for (let item of dockAppList) {
            if (item.key == app.key) {
                return true;
            }
        }
        return false;
    },
    /**
     * @description: APP是否打开
     */
    isAppInOpenList(app, openAppList) {
        for (let item of openAppList) {
            if (item.key == app.key) {
                return true;
            }
        }
        return false;
    },
    /**
     * @description: 获取指定key的App
     */
    getAppByKey(key) {
        let appList = AppModel.allAppList
        for (let app of appList) {
            if (app.key == key) {
                return app
            }
        }
        return false
    },
    /**
     * @description: 获取桌面App列表
     */
    getDeskTopApp() {
        return AppModel.allAppList
    },
    /**
     * @description: 格式化时间
     * @param {any} date
     * @param {string} format
     */
    formatTime(date, format) {
        if (!date) return;
        if (!format) format = "yyyy-MM-dd";
        switch (typeof date) {
            case "string":
                date = new Date(date.replace(/-/, "/"));
                break;
            case "number":
                date = new Date(date);
                break;
            default:
        }
        var dict = {
            "yyyy": date.getFullYear(),
            "M": date.getMonth() + 1,
            "d": date.getDate(),
            "H": date.getHours(),
            "m": date.getMinutes(),
            "s": date.getSeconds(),
            "MM": ("" + (date.getMonth() + 101)).substr(1),
            "dd": ("" + (date.getDate() + 100)).substr(1),
            "HH": ("" + (date.getHours() + 100)).substr(1),
            "mm": ("" + (date.getMinutes() + 100)).substr(1),
            "ss": ("" + (date.getSeconds() + 100)).substr(1)
        };
        return format.replace(/(yyyy|MM?|dd?|HH?|ss?|mm?)/g, function () {
            return dict[arguments[0]];
        });
    }
}