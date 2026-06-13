<script>
  import { onMount, tick } from 'svelte';
  import { api, ApiError } from '../lib/api.js';
  import { viewport } from '../lib/viewport.svelte.js';
  import { nextEntryIdAfter } from '../lib/entryCache.svelte.js';
  import ActionToolbar from './ActionToolbar.svelte';

  let { entryId, user = null } = $props();

  let entry = $state(null);
  let content = $state(null);
  let externalOnly = $state(false);
  let loading = $state(true);
  let error = $state(null);
  let currentPage = $state(0);
  let totalPages = $state(1);

  let innerEl = $state(null);

  async function load() {
    loading = true;
    error = null;
    currentPage = 0;
    try {
      const data = await api.entryContent(entryId);
      entry = data;
      content = data.content_full;
      externalOnly = !!data.external_only;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = '/auth/login';
        return;
      }
      error = err.message;
    } finally {
      loading = false;
    }

    // Once the current entry is loaded, fire-and-forget a fetch of the next
    // entry's content so it's warm in the server's cache when we get there.
    const nextId = nextEntryIdAfter(entryId);
    if (nextId) api.entryContentPrefetch(nextId).catch(() => { /* best-effort */ });
  }

  $effect(() => {
    entryId; // trigger when prop changes
    load();
  });

  $effect(() => {
    const _ = `${viewport.w}:${viewport.h}:${content ? content.length : 0}`;
    void _;
    measure();
  });

  async function measure() {
    await tick();
    if (!innerEl) return;
    const pageWidth = viewport.w;
    totalPages = Math.max(1, Math.ceil(innerEl.scrollWidth / pageWidth));
    if (currentPage >= totalPages) currentPage = totalPages - 1;
  }

  function next() {
    if (currentPage < totalPages - 1) currentPage += 1;
  }

  function prev() {
    if (currentPage > 0) currentPage -= 1;
  }

  function onKey(e) {
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
      e.preventDefault();
      next();
    } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      e.preventDefault();
      prev();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      window.history.back();
    }
  }

  onMount(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  function onTap(e) {
    if (e.target.closest('a, button')) return;
    const x = e.clientX;
    if (x < viewport.w / 4) prev();
    else if (x > (viewport.w * 3) / 4) next();
  }

  function onEntryChange(updated) {
    entry = { ...entry, ...updated };
  }
</script>

<div class="reader">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="page-area" onclick={onTap}>
    {#if loading}
      <p class="status">Loading…</p>
    {:else if error}
      <p class="status error">{error}</p>
    {:else if externalOnly}
      <div class="status">
        <p>This entry isn't readable inside the app.</p>
        {#if entry?.target_url}
          <p><a href={entry.target_url} target="_blank" rel="noopener">Open at source</a></p>
        {/if}
      </div>
    {:else if content}
      <div
        class="inner"
        bind:this={innerEl}
        style="transform: translateX(-{currentPage * viewport.w}px)"
      >
        {@html content}
      </div>
    {/if}
  </div>

  {#if entry && !loading}
    <ActionToolbar entry={entry} hasKindle={user?.has_kindle} onChange={onEntryChange} />
  {/if}

  {#if !loading && !externalOnly && content}
    <div class="pager">
      <button onclick={prev} disabled={currentPage === 0}>‹</button>
      <span>{currentPage + 1} / {totalPages}</span>
      <button onclick={next} disabled={currentPage >= totalPages - 1}>›</button>
    </div>
  {/if}
</div>

<style>
  .reader {
    display: flex;
    flex-direction: column;
    width: 100vw;
    height: calc(100vh - 2.4em);
  }
  .page-area {
    flex: 1 1 auto;
    overflow: hidden;
    position: relative;
  }
  .inner {
    column-width: 100vw;
    column-gap: 0;
    column-fill: auto;
    height: 100%;
    padding: 0 1em;
    box-sizing: border-box;
    will-change: transform;
  }
  .inner :global(img),
  .inner :global(video),
  .inner :global(iframe) {
    display: block;
    max-width: 100%;
    max-height: 90%;
    height: auto;
    margin: 0.5em auto;
    object-fit: contain;
    break-inside: avoid;
  }
  .inner :global(figure) {
    margin: 0.5em 0;
    break-inside: avoid;
  }
  .inner :global(figcaption) {
    font-size: 0.85em;
    color: #555;
    text-align: center;
  }
  .inner :global(pre),
  .inner :global(table) {
    overflow: hidden;
    white-space: pre-wrap;
    break-inside: avoid;
    max-width: 100%;
  }
  .inner :global(blockquote) {
    margin: 0.5em 0;
    padding-left: 1em;
    border-left: 2px solid #888;
    break-inside: avoid;
  }
  .inner :global(h1), .inner :global(h2), .inner :global(h3) {
    break-after: avoid;
  }
  .pager {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3em 0.8em;
    background: #fff;
    border-top: 1px solid #ccc;
    font-size: 0.9em;
    box-sizing: border-box;
  }
  .pager button {
    min-width: 3em;
    padding: 0.3em 0.8em;
  }
  .pager button:disabled {
    color: #999;
    border-color: #ccc;
  }
  .status { padding: 1em; color: #555; }
  .status.error { color: #800; }
</style>
