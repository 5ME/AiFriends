/**
 * 自动根据 Vite MODE 切换环境，不再手动改 platform 变量：
 * - npm run dev  → MODE=development → 使用 devPlatform（默认 django）
 * - npm run build → MODE=production  → 使用 cloud 模式，URL 从环境变量注入
 *
 * 开发时可设置 VITE_PLATFORM 覆盖：VITE_PLATFORM=vue npm run dev
 * 生产部署可设置 VITE_CLOUD_BASE：VITE_CLOUD_BASE=https://your-server npm run build
 */
const isBuild = import.meta.env.MODE === 'production'
const platform = import.meta.env.VITE_PLATFORM || (isBuild ? 'cloud' : 'django')

const CLOUD_BASE = import.meta.env.VITE_CLOUD_BASE || 'https://115.190.245.146'

const CONFIG_API = {
  HTTP_URL: '',
  VAD_URL: '',
}

if (!isBuild && platform === 'vue') {
  CONFIG_API.HTTP_URL = 'http://127.0.0.1:8000'
  CONFIG_API.VAD_URL = 'http://localhost:5173/vad/'
} else if (!isBuild && platform === 'django') {
  CONFIG_API.HTTP_URL = 'http://127.0.0.1:8000'
  CONFIG_API.VAD_URL = 'http://127.0.0.1:8000/static/frontend/vad/'
} else {
  // npm run build — 生产模式，URL 从环境变量读取
  CONFIG_API.HTTP_URL = CLOUD_BASE
  CONFIG_API.VAD_URL = `${CLOUD_BASE}/static/frontend/vad/`
}

export default CONFIG_API