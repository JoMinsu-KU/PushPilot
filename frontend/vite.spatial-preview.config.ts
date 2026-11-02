import { defineConfig } from 'vite';

/** A local design entry with no API proxy or equipment connection. */
export default defineConfig({
  cacheDir: 'node_modules/.vite-spatial-preview',
  plugins: [{ name: 'spatial-preview-only', configureServer(server) {
    server.middlewares.use((request, response, next) => {
      if (request.url === '/') { response.writeHead(302, { Location: '/spatial-preview.html' }); response.end(); return; }
      if (/^\/api(?:\/|\?|$)/.test(request.url ?? '')) {
        response.writeHead(404, { 'Content-Type': 'application/json' });
        response.end('{"detail":"No API in the Spatial design preview."}'); return;
      }
      next();
    });
  } }],
  server: { host: '127.0.0.1', port: 9220, strictPort: true },
  build: { target: 'es2022', sourcemap: false, outDir: 'dist-spatial-preview',
    rollupOptions: { input: 'spatial-preview.html' } },
});
