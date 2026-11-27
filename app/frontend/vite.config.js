import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig(({ command }) => {
  const backend = process.env.SUBGUARD_BACKEND_URL || 'http://localhost:8000';

  return {
    base: command === 'build' ? '/static/frontend/' : '/',
    plugins: [react(), tailwindcss()],
    server: {
      proxy: { '/api': backend, '/auth': backend, '/demo': backend },
    },
  };
});
