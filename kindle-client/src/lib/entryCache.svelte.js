// Tiny shared cache holding the most recently rendered entry list, so the
// reader can find which entry comes next and prefetch its content.

export const entryCache = $state({ entries: [] });

export function setEntries(entries) {
  entryCache.entries = entries;
}

export function nextEntryIdAfter(id) {
  const list = entryCache.entries;
  const i = list.findIndex((e) => String(e.id) === String(id));
  if (i < 0 || i >= list.length - 1) return null;
  return list[i + 1].id;
}
