/**
 * <ul>
 * <li><code>vue</code>: 前端模式（开发阶段）</li>
 * <li><code>django</code>: 后端模式（开发阶段）</li>
 * <li><code>cloud</code>: 云端模式（上线阶段）</li>
 * </ul>
 */
const platform = 'django'

const CONFIG_API = {
  HTTP_URL: "",
  VAD_URL: "",
}

if (platform === "vue") {
  CONFIG_API.HTTP_URL = "http://127.0.0.1:8000"
  CONFIG_API.VAD_URL = "http://localhost:5173/vad/"
} else if (platform === "django") {
  CONFIG_API.HTTP_URL = "http://127.0.0.1:8000"
  CONFIG_API.VAD_URL = "http://127.0.0.1:8000/static/frontend/vad/"
} else if (platform === "cloud") {
  CONFIG_API.HTTP_URL = "http://115.190.245.146"
  CONFIG_API.VAD_URL = "http://115.190.245.146/static/frontend/vad/"
}

export default CONFIG_API