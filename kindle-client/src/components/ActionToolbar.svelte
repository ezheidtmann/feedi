<script>
  import { api } from '../lib/api.js';

  let { entry, hasKindle = false, onChange } = $props();

  let busy = $state(null); // 'pin' | 'favorite' | 'kindle' while a request is in flight

  async function run(kind, fn) {
    if (busy) return;
    busy = kind;
    try {
      const updated = await fn();
      if (onChange) onChange(updated || entry);
    } catch (err) {
      console.error(err);
    } finally {
      busy = null;
    }
  }

  function togglePin() {
    run('pin', async () => {
      if (entry.pinned) {
        await api.unpin(entry.id);
        return { ...entry, pinned: null };
      } else {
        return await api.pin(entry.id);
      }
    });
  }

  function toggleFavorite() {
    run('favorite', async () => {
      if (entry.favorited) {
        await api.unfavorite(entry.id);
        return { ...entry, favorited: null };
      } else {
        return await api.favorite(entry.id);
      }
    });
  }

  function sendKindle() {
    if (entry.sent_to_kindle) return;
    run('kindle', async () => await api.sendToKindle(entry.id));
  }
</script>

<div class="bar">
  <button onclick={togglePin} disabled={busy === 'pin'}>
    {entry.pinned ? '★ Pinned' : '☆ Pin'}
  </button>
  <button onclick={toggleFavorite} disabled={busy === 'favorite'}>
    {entry.favorited ? '♥ Favorited' : '♡ Favorite'}
  </button>
  {#if hasKindle}
    <button onclick={sendKindle} disabled={!!entry.sent_to_kindle || busy === 'kindle'}>
      {entry.sent_to_kindle ? 'Sent to Kindle' : 'Send to Kindle'}
    </button>
  {/if}
</div>

<style>
  .bar {
    display: flex;
    gap: 0.4em;
    padding: 0.3em 0.8em;
    border-top: 1px solid #ccc;
    background: #fff;
    font-size: 0.9em;
  }
  button {
    flex: 1;
    padding: 0.4em 0.4em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  button:disabled {
    color: #999;
    border-color: #ccc;
  }
</style>
