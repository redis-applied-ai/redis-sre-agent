import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@radar/ui-kit': resolve(__dirname, '../src/index.ts'),
      '@radar/ui-kit/styles': resolve(__dirname, '../src/styles/index.css'),
    },
  },
});
