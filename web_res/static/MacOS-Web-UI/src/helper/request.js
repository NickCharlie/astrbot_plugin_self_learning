import axios from 'axios'
import tool from "./tool"
import config from "@/config"

import { ElMessage } from 'element-plus'
const HTTP_STATUS_CODE = config.httpStatusCode
const DEFAULT_ERROR_MESSAGE = config.defaultErrorMessage
/**
 * 高度封装的请求方法
 * 支持参数 url,method,header,data,success,error
 * @param {object} 请求参数对象
 * @param {object} 如需要回调 请原封不动传入
 */
function request(data, object = {}) {
    data.success = object.success || data.success
    if (!data.success || typeof data.success !== 'function') {
        data.success = false
    }

    data.error = object.error || data.error
    if (!data.error || typeof data.error !== 'function') {
        data.error = false
    }

    data.final = object.final || data.final
    if (!data.final || typeof data.final !== 'function') {
        data.final = false
    }

    if (!data.data) {
        data.data = {}
    }

    if (data.url.indexOf("https://") < 0 && data.url.indexOf("http://") < 0) {
        //相对地址 追加 apiBaseUrl
        data.url = config.apiBaseUrl + data.url
    }

    //处理请求方法 默认GET
    data.method = data.method || "get"

    //默认header
    let header = {
        'Content-Type': 'application/json',
        'Version': config.version,
    }
    //自定义header
    if (data.header) {
        if (typeof data.header == "object" && data.header instanceof Array) {
            for (let i in data.header) {
                header[i] = data.header[i]
            }
        }
    }
    //如未指定不需要传TOKEN，则默认带上
    if (!data.noToken) {
        header['Authorization'] = tool.getAccessToken()
    }

    let axiosResource = false

    //走不同的请求方法
    switch (data.method.toLowerCase()) {
        case 'post':
            axiosResource = axios.post(data.url, data.data, {
                headers: header
            })
            break
        case 'put':
            axiosResource = axios.put(data.url, data.data, {
                headers: header
            })
            break
        case 'delete':
            axiosResource = axios.delete(data.url, {
                headers: header
            })
            break
        default:
            axiosResource = axios.get(data.url, {
                headers: header
            })
    }
    axiosResource.then(function (response) {
        switch (response.data.code) {
            case HTTP_STATUS_CODE.OK:
                data.success ? data.success(response.data) :
                    ElMessage.success({
                        message: response.data.msg || DEFAULT_ERROR_MESSAGE,
                        type: 'warning',
                    })
                break
            default:
                data.error ? (
                    data.error(response.data) ? false :
                        ElMessage.warning({
                            message: response.data.msg || DEFAULT_ERROR_MESSAGE,
                            type: 'warning',
                        })
                ) : ElMessage.warning({
                    message: response.data.msg || DEFAULT_ERROR_MESSAGE,
                    type: 'warning',
                })
        }
        data.final && data.final()
    })
        .catch(function (error) {
            config.debug && console.log(error)
            ElMessage.warning({
                message: DEFAULT_ERROR_MESSAGE,
                type: 'warning',
            })
            data.final && data.final()
        })
}
export default request