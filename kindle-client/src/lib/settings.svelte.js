// User-tunable settings persisted to localStorage. Applies font-size as a CSS
// variable on :root so the whole app rescales on change.

const KEY = 'feedi-kindle-settings';

const defaults = {
  fontSize: 'medium',
  hideSeen: true,
};

const FONT_PX = {
  small: 16,
  medium: 18,
  large: 22,
  xlarge: 26,
};

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    return { ...defaults, ...(raw ? JSON.parse(raw) : {}) };
  } catch (e) {
    return { ...defaults };
  }
}

export const settings = $state(load());

export const FONT_SIZE_OPTIONS = [
  { value: 'small',  label: 'Small'  },
  { value: 'medium', label: 'Medium' },
  { value: 'large',  label: 'Large'  },
  { value: 'xlarge', label: 'X-Large' },
];

function applyFontSize() {
  const px = FONT_PX[settings.fontSize] || FONT_PX.medium;
  document.documentElement.style.setProperty('--base-font-size', `${px}px`);
}

applyFontSize();

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...settings }));
  } catch (e) { /* ignore quota errors */ }
}

export function setFontSize(value) {
  settings.fontSize = value;
  applyFontSize();
  persist();
}

export function setHideSeen(value) {
  settings.hideSeen = !!value;
  persist();
}
