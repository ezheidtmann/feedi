<script>
  import { onMount, tick } from 'svelte';
  import { api, ApiError } from '../lib/api.js';
  import { viewport } from '../lib/viewport.svelte.js';
  import { settings } from '../lib/settings.svelte.js';
  import { computePageStarts } from '../lib/paging.js';
  import { setEntries } from '../lib/entryCache.svelte.js';
  import EntryCard from './EntryCard.svelte';

  let { kind = 'entries', params = {} } = $props();

  let entries = $state([]);
  let nextCursor = $state(null);
  let loading = $state(false);
  let error = $state(null);
  let currentPage = $state(0);

  let cardRefs = $state([]);
  let pageStarts = $state([0]);

  let containerEl = $state(null);
  let listEl = $state(null);

  async function fetchPage() {
    if (loading) return;
    loading = true;
    try {
      const queryParams = { ...params };
      if (kind !== 'pinned') {
        // Translate the user setting into the API param.
        queryParams.hide_seen = settings.hideSeen ? '1' : '0';
        queryParams.cursor = nextCursor || undefined;
      }
      const data =
        kind === 'pinned'
          ? await api.pinned(queryParams)
          : await api.entries(queryParams);
      if (kind === 'pinned') {
        entries = data.entries;
        nextCursor = null;
      } else {
        entries = [...entries, ...data.entries];
        nextCursor = data.next_cursor;
      }
      setEntries(entries);
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

  // Reload from scratch whenever the filter or hideSeen setting changes.
  $effect(() => {
    const _ = `${kind}:${JSON.stringify(params)}:${settings.hideSeen}`;
    void _;
    entries = [];
    nextCursor = null;
    currentPage = 0;
    pageStarts = [0];
    cardRefs = [];
    fetchPage();
  });

  // Re-measure pages whenever entries or viewport dimensions change.
  $effect(() => {
    const _ = `${entries.length}:${viewport.w}:${viewport.h}`;
    void _;
    measurePages();
  });

  async function measurePages() {
    await tick();
    if (!listEl) return;
    const containerHeight = viewport.h - listEl.getBoundingClientRect().top - 30;
    pageStarts = computePageStarts(cardRefs, containerHeight);
    if (currentPage >= pageStarts.length) currentPage = Math.max(0, pageStarts.length - 1);
  }

  const yOffset = $derived(cardRefs[pageStarts[currentPage]]?.offsetTop ?? 0);

  function next() {
    if (currentPage < pageStarts.length - 1) {
      currentPage += 1;
    } else if (nextCursor) {
      fetchPage();
    }
  }

  function prev() {
    if (currentPage > 0) currentPage -= 1;
  }

  // Pre-fetch when within one page of the end of currently-loaded entries.
  $effect(() => {
    if (kind === 'pinned') return;
    if (!nextCursor || loading) return;
    if (currentPage >= pageStarts.length - 2) {
      fetchPage();
    }
  });

  function onKey(e) {
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
      e.preventDefault();
      next();
    } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      e.preventDefault();
      prev();
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
<div class="list-container" bind:this={containerEl} onclick={onTap}>
  {#if error}
    <p class="error">{error}</p>
  {:else if entries.length === 0 && !loading}
    <p class="empty">No entries.</p>
  {/if}

  <div class="list" bind:this={listEl} style="transform: translateY(-{yOffset}px)">
    {#each entries as entry, i (entry.id)}
      <div bind:this={cardRefs[i]}>
        <EntryCard {entry} />
      </div>
    {/each}
  </div>

  <div class="pager">
    <button onclick={prev} disabled={currentPage === 0}>‹</button>
    <span>{currentPage + 1} / {pageStarts.length}{nextCursor ? '+' : ''}</span>
    <button onclick={next} disabled={currentPage >= pageStarts.length - 1 && !nextCursor}>›</button>
  </div>
</div>

<style>
  .list-container {
    position: relative;
    width: 100vw;
    height: calc(100vh - 2.4em);
    overflow: hidden;
  }
  .list {
    padding: 0 0.8em;
    transition: none;
    will-change: transform;
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
  .pager button:disabled {
    color: #999;
    border-color: #ccc;
  }
  .empty, .error {
    padding: 1em 0.8em;
    color: #555;
  }
  .error { color: #800; }
</style>
