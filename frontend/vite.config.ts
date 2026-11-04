// Vite config for the operator workspace: dev API proxy plus the web build.
// Local dev/build settings only; no equipment or provider connection.
import { defineConfig } from 'vite';

export default defineConfig({
  server: { proxy: { '/api': 'http://127.0.0.1:8080' } },
  build: { target: 'es2022', sourcemap: false },
});
