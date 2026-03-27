/*
 * 功能：在每个请求头里自动添加`access token`。
 * 然后拦截请求结果，如果返回结果是身份认证失败（401），
 * 则说明`access_token`过期了，
 * 那么先用`cookie`中的`refresh_token`刷新`access_token`。
 * 如果刷新失败则说明`refresh_token`也过期了，
 * 则调用`user.logout()`在浏览器内存中删除登录状态；
 * 如果刷新成功，则重新发送原请求。
*/

import axios from "axios"
import {useUserStore} from "@/stores/user.js";

const BASE_URL = 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,  // 允许携带跨域 Cookie，用于刷新令牌时传递 refresh_token 的 cookie
})

// 请求拦截器：在每次请求发送前，从 store 中获取 accessToken，并添加到请求头的 Authorization 字段中
api.interceptors.request.use(config => {
  const user = useUserStore()
  // 如果用户存在且有访问令牌，在请求头中添加 Authorization 字段
  if (user.accessToken) {
    config.headers.Authorization = `Bearer ${user.accessToken}`
  }
  return config
})

// 标记是否正在刷新令牌，防止多个并发请求同时触发刷新
let isRefreshing = false
// 存储等待刷新完成的请求回调
let refreshSubscribers = []

/**
 * 订阅令牌刷新事件
 * @param {function} callback - 令牌刷新成功后的回调函数
 */
function subscribeTokenRefresh(callback) {
  refreshSubscribers.push(callback)
}

/**
 * 通知所有订阅者令牌已刷新
 * @param {string} token - 新的访问令牌
 */
function onRefreshed(token) {
  // 遍历所有订阅者并执行回调（传入token）
  refreshSubscribers.forEach(cb => cb(token))
  // 清空订阅者列表
  refreshSubscribers = []
}

/**
 * 通知所有订阅者令牌刷新失败
 * @param {Error} err - 错误对象
 */
function onRefreshFailed(err) {
  // 遍历所有订阅者并执行回调（传入错误）
  refreshSubscribers.forEach(cb => cb(null, err))
  // 清空订阅者列表
  refreshSubscribers = []
}

// 响应拦截器：处理响应错误，特别是 401 未授权错误
api.interceptors.response.use(
    // 成功响应直接返回
    response => response,
    // 处理错误响应
    async error => {
      const user = useUserStore()
      // 获取原始请求配置，如果没有原始请求配置，直接拒绝错误
      const originalRequest = error?.config
      if (!originalRequest) {
        return Promise.reject(error)
      }

      // 检查是否是 401 未授权错误，且该请求未被重试过（避免无限循环）
      if (error.response?.status === 401 && !originalRequest._retry) {
        // 标记该请求已被重试，避免无限循环
        originalRequest._retry = true

        // 返回一个 Promise，等待令牌刷新完成后再重新发起请求
        return new Promise((resolve, reject) => {
          // 订阅令牌刷新事件，当令牌刷新完成时（成功或失败）会被调用
          subscribeTokenRefresh((token, error) => {
            if (error) {
              // 刷新失败，拒绝当前请求
              reject(error)
            } else {
              // 刷新成功，用新 token 更新原始请求的 Authorization 头
              originalRequest.headers.Authorization = `Bearer ${token}`
              // 重新发起原始请求，并将结果 resolve
              resolve(api(originalRequest))
            }
          })

          // 如果当前没有正在刷新令牌
          if (!isRefreshing) {
            // 设置刷新状态为 true，发送刷新令牌请求
            isRefreshing = true
            axios.post(
                `${BASE_URL}/api/user/account/refresh_token/`,
                {},
                {withCredentials: true, timeout: 5000}
            ).then(res => {
              // 刷新成功，更新用户状态中的访问令牌，通知所有订阅者令牌已刷新
              user.setAccessToken(res.data.access_token)
              onRefreshed(res.data.access_token)
            }).catch(error => {
              // 刷新失败，执行用户登出，并通知所有订阅者刷新失败，拒绝当前请求
              user.logout()
              onRefreshFailed(error)
              reject(error)
            }).finally(() => {
              // 无论成功失败，设置刷新状态为 false
              isRefreshing = false
            })
          }
        })
      }

      // 对于非 401 错误，或者已经重试过，直接拒绝
      return Promise.reject(error)
    }
)

export default api
