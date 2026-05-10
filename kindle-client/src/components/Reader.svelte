<script>
  import { onMount, tick } from 'svelte';
  import { api, ApiError } from '../lib/api.js';
  import { viewport } from '../lib/viewport.svelte.js';

  let { entryId } = $props();

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
  }

  $effect(() => {
    entryId; // trigger when prop changes
    load();
  });

  $effect(() => {
    // re-measure totalPages on viewport change or content change
    const _ = `${viewport.w}:${viewport.h}:${content ? content.length : 0}`;
    void _;
    measure();
  });

  async function measure() {
    await tick();
    if (!innerEl) return;
    const pageWidth = viewport.w;
    const total = Math.max(1, Math.ceil(innerEl.scrollWidth / pageWidth));
    totalPages = total;
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
    // middle 50%: do nothing (or open menu in the future)
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="reader" onclick={onTap}>
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

    <div class="pager">
      <button onclick={prev} disabled={currentPage === 0}>‹</button>
      <span>{currentPage + 1} / {totalPages}</span>
      <button onclick={next} disabled={currentPage >= totalPages - 1}>›</button>
    </div>
  {/if}
</div>

<style>
  .reader {
    position: relative;
    width: 100vw;
    height: calc(100vh - 2.4em);
    overflow: hidden;
  }
  .inner {
    column-width: 100vw;
    column-gap: 0;
    column-fill: auto;
    height: calc(100vh - 2.4em - 1.8em);
    padding: 0 1em;
    box-sizing: border-box;
    will-change: transform;
  }
  .inner :global(img),
  .inner :global(video),
  .inner :global(iframe) {
    max-width: 100%;
    max-height: 100%;
    height: auto;
    break-inside: avoid;
  }
  .inner :global(figure) { margin: 0.5em 0; }
  .inner :global(pre) {
    overflow: hidden;
    white-space: pre-wrap;
    break-inside: avoid;
  }
  .inner :global(blockquote) {
    margin: 0.5em 0;
    padding-left: 1em;
    border-left: 2px solid #888;
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
