<script>
  import { onMount, tick } from 'svelte';
  import { api, ApiError } from '../lib/api.js';
  import { viewport } from '../lib/viewport.svelte.js';
  import { computePageStarts } from '../lib/paging.js';

  let feeds = $state([]);
  let folders = $state([]);
  let loading = $state(true);
  let error = $state(null);
  let currentPage = $state(0);

  let itemRefs = $state([]);
  let pageStarts = $state([0]);
  let listEl = $state(null);

  // Build a single flat list of items: a folder header followed by its feeds,
  // then loose feeds (no folder) at the end.
  const items = $derived.by(() => {
    if (!feeds.length) return [];
    const groups = new Map();
    const loose = [];
    for (const f of feeds) {
      if (f.folder) {
        if (!groups.has(f.folder)) groups.set(f.folder, []);
        groups.get(f.folder).push(f);
      } else {
        loose.push(f);
      }
    }
    const sortedFolders = [...groups.keys()].sort((a, b) => a.localeCompare(b));
    const out = [];
    for (const folder of sortedFolders) {
      out.push({ kind: 'folder', name: folder });
      for (const f of groups.get(folder)) out.push({ kind: 'feed', feed: f });
    }
    for (const f of loose.sort((a, b) => a.name.localeCompare(b.name))) {
      out.push({ kind: 'feed', feed: f });
    }
    return out;
  });

  async function load() {
    try {
      const [feedsRes, foldersRes] = await Promise.all([api.feeds(), api.folders()]);
      feeds = feedsRes.feeds;
      folders = foldersRes.folders;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = '/auth/login';
        return;
      }
      error = err.message;
    } finally {
      loading = false;
    }
  }

  onMount(load);

  $effect(() => {
    const _ = `${items.length}:${viewport.w}:${viewport.h}`;
    void _;
    measure();
  });

  async function measure() {
    await tick();
    if (!listEl) return;
    const containerHeight = viewport.h - listEl.getBoundingClientRect().top - 30;
    pageStarts = computePageStarts(itemRefs, containerHeight);
    if (currentPage >= pageStarts.length) currentPage = Math.max(0, pageStarts.length - 1);
  }

  const yOffset = $derived(itemRefs[pageStarts[currentPage]]?.offsetTop ?? 0);

  function next() {
    if (currentPage < pageStarts.length - 1) currentPage += 1;
  }
  function prev() {
    if (currentPage > 0) currentPage -= 1;
  }

  function onKey(e) {
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
      e.preventDefault(); next();
    } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      e.preventDefault(); prev();
    }
  }

  onMount(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  function onTap(e) {
    if (e.target.closest('a, button')) return;
    const x = e.clientX;
    if (x < viewport.w / 3) prev();
    else if (x > (viewport.w * 2) / 3) next();
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="container" onclick={onTap}>
  {#if loading}
    <p class="status">Loading…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else if items.length === 0}
    <p class="status">No feeds yet.</p>
  {:else}
    <div class="list" bind:this={listEl} style="transform: translateY(-{yOffset}px)">
      {#each items as item, i}
        <div bind:this={itemRefs[i]}>
          {#if item.kind === 'folder'}
            <a class="folder" href="#/folder/{encodeURIComponent(item.name)}">{item.name}</a>
          {:else}
            <a class="feed" href="#/feed/{item.feed.id}">{item.feed.name}</a>
          {/if}
        </div>
      {/each}
    </div>

    <div class="pager">
      <button onclick={prev} disabled={currentPage === 0}>‹</button>
      <span>{currentPage + 1} / {pageStarts.length}</span>
      <button onclick={next} disabled={currentPage >= pageStarts.length - 1}>›</button>
    </div>
  {/if}
</div>

<style>
  .container {
    position: relative;
    width: 100vw;
    height: calc(100vh - 2.4em);
    overflow: hidden;
  }
  .list {
    padding: 0.4em 0.8em;
    will-change: transform;
  }
  .folder {
    display: block;
    margin: 0.6em 0 0.2em 0;
    font-weight: bold;
    text-decoration: none;
    color: #000;
    border-bottom: 1px solid #000;
    padding: 0.2em 0;
  }
  .feed {
    display: block;
    padding: 0.5em 0 0.5em 1em;
    text-decoration: none;
    color: #000;
    border-bottom: 1px solid #ddd;
  }
  .pager {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3em 0.8em;
    background: #fff;
    border-top: 1px solid #ccc;
    font-size: 0.9em;
  }
  .pager button {
    min-width: 3em;
    padding: 0.3em 0.8em;
  }
  .pager button:disabled { color: #999; border-color: #ccc; }
  .status { padding: 1em; color: #555; }
  .status.error { color: #800; }
</style>
