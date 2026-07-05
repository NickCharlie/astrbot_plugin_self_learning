import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import solidPlugin from 'vite-plugin-solid';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// 生产构建产物直接落到插件静态目录，由 Quart 的 /static 路径提供服务。
const dashboardOutDir = path.resolve(__dirname, '../web_res/static/dashboard');

export default defineConfig(({ command }) => ({
  plugins: [solidPlugin()],
  // 开发服务器保持根路径；生产构建使用 /static/dashboard/ 前缀，
  // 这样 index.html 内的资源引用能命中 Quart 的 static 路由。
  base: command === 'build' ? '/static/dashboard/' : '/',
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_DASHBOARD_PROXY || 'http://127.0.0.1:7833',
        changeOrigin: true,
      },
      '/static': {
        target: process.env.VITE_DASHBOARD_PROXY || 'http://127.0.0.1:7833',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'esnext',
    outDir: dashboardOutDir,
    // outDir 位于 web_src 之外，显式允许清空以保证每次干净重建。
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
}));
