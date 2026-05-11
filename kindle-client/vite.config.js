import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// Assets are served by Flask under /static/kindle/, and index.html is served at /k/.
// Vite emits asset URLs prefixed with `base` so the deployed bundle resolves correctly.
export default defineConfig({
  plugins: [svelte()],
  base: '/static/kindle/',
  build: {
    outDir: '../feedi/static/kindle',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:9988',
      '/auth': 'http://localhost:9988',
    },
  },
});
