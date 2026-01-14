import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@radar/ui-kit': resolve(__dirname, 'ui-kit/src'),
      '@radar/ui-kit/styles': resolve(__dirname, 'ui-kit/src/styles/index.css'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: ["gt43y0t0jf-andrew-brookins-1", "gt43y0t0jf-andrew-brookins-1.taila74d4.ts.net", "localhost"],
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8080',
        changeOrigin: true,
        ws: true, // Enable WebSocket proxying
      },
      '/health': {
        target: process.env.VITE_API_URL || 'http://localhost:8080',
        changeOrigin: true,
      },
      '/metrics': {
        target: process.env.VITE_API_URL || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
});
