// Given an array of measured DOM elements and an available height, return the
// indexes at which each viewport-sized page should start. Used by EntryList
// and FeedList to lay out items without splitting one across screens.

export function computePageStarts(refs, containerHeight) {
  if (containerHeight <= 0) return [0];
  const starts = [0];
  let pageTop = refs[0]?.offsetTop ?? 0;
  for (let i = 1; i < refs.length; i++) {
    const el = refs[i];
    if (!el) continue;
    const bottom = el.offsetTop + el.offsetHeight;
    if (bottom - pageTop > containerHeight) {
      starts.push(i);
      pageTop = el.offsetTop;
    }
  }
  return starts;
}
