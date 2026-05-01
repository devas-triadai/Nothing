import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const uiPort = parseInt(env.VITE_AGENT_UI_PORT || '7860', 10);
  const apiPort = env.VITE_AGENT_API_PORT || '8005';

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: uiPort,
      proxy: {
        '/api/agent': {
          target: `http://localhost:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  };
});
