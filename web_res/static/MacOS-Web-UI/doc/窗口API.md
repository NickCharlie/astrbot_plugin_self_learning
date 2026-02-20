## 窗口API说明文档

```
/**
* @description: 打开上一次的应用
*/
openTheLastApp()

/**
* @description: 最小化应用
*/
hideApp(app)

/**
* @description: 根据PID关闭应用
*/
closeWithPid(pid)

/**
* @description: 关闭应用
*/
closeApp(app)

/**
* @description: 打开应用
*/
openApp(app)

/**
* @description: 显示并置顶APP
*/
showApp(app)

/**
* @description: 根据key打开APP
*/
openAppByKey(key)

/**
* @description: 带参数打开App
*/
openWithData(data)

/**
* @description: 获取常驻Dock的App列表
*/
getDockAppList()
```