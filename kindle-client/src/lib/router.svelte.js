// Minimal hash router. Routes are described as patterns like "/feed/:id".
// Parses window.location.hash on load and on hashchange.

const PATTERNS = [
  { name: 'home',       pattern: /^#?\/?$/ },
  { name: 'favorites',  pattern: /^#?\/favorites\/?$/ },
  { name: 'pinned',     pattern: /^#?\/pinned\/?$/ },
  { name: 'kindle',     pattern: /^#?\/kindle\/?$/ },
  { name: 'feed',       pattern: /^#?\/feed\/(\d+)\/?$/,        params: ['id'] },
  { name: 'folder',     pattern: /^#?\/folder\/([^/]+)\/?$/,    params: ['name'] },
  { name: 'entry',      pattern: /^#?\/entry\/(\d+)\/?$/,       params: ['id'] },
];

function parse(hash) {
  const h = hash || '#/';
  for (const route of PATTERNS) {
    const m = h.match(route.pattern);
    if (m) {
      const params = {};
      (route.params || []).forEach((name, i) => {
        params[name] = decodeURIComponent(m[i + 1]);
      });
      return { name: route.name, params };
    }
  }
  return { name: 'home', params: {} };
}

export const route = $state(parse(window.location.hash));

window.addEventListener('hashchange', () => {
  const next = parse(window.location.hash);
  route.name = next.name;
  route.params = next.params;
});

export function navigate(hash) {
  if (window.location.hash === hash) return;
  window.location.hash = hash;
}

export function back() {
  window.history.back();
}
