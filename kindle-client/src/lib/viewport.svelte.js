// Tracks the visual viewport size. visualViewport is preferred (more accurate
// on mobile-ish browsers); falls back to window.innerWidth/Height.

export const viewport = $state({ w: window.innerWidth, h: window.innerHeight });

function measure() {
  const vv = window.visualViewport;
  viewport.w = vv ? vv.width : window.innerWidth;
  viewport.h = vv ? vv.height : window.innerHeight;
}

measure();
window.addEventListener('resize', measure);
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', measure);
}
