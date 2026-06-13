<script>
  let { entry } = $props();

  function sourceLabel(e) {
    if (e.display_name) return e.display_name;
    if (e.username) return e.username;
    return e.feed?.name || '';
  }

  function shortDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }
</script>

<a class="card" href="#/entry/{entry.id}" class:viewed={entry.viewed}>
  {#if entry.header}
    <div class="header">{@html entry.header}</div>
  {/if}
  <div class="title">{entry.title || '(untitled)'}</div>
  <div class="meta">
    <span>{sourceLabel(entry)}</span>
    <span class="date">{shortDate(entry.display_date || entry.sort_date)}</span>
  </div>
  {#if entry.content_short}
    <div class="excerpt">{@html entry.content_short}</div>
  {/if}
</a>

<style>
  .card {
    display: block;
    padding: 0.6em 0;
    color: #000;
    text-decoration: none;
    border-bottom: 1px solid #ccc;
  }
  .header {
    font-size: 0.85em;
    color: #555;
    margin-bottom: 0.2em;
  }
  .title {
    font-weight: bold;
    font-size: 1.05em;
    line-height: 1.3;
  }
  .meta {
    display: flex;
    justify-content: space-between;
    font-size: 0.85em;
    color: #555;
    margin-top: 0.2em;
  }
  .excerpt {
    margin-top: 0.3em;
    font-size: 0.9em;
    color: #333;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .excerpt :global(p) { margin: 0; }
  .viewed .title { color: #777; font-weight: normal; }
</style>
