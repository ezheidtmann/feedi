<script>
  import { onMount } from 'svelte';
  import { api, ApiError } from './lib/api.js';
  import { route, back } from './lib/router.svelte.js';
  import TopBar from './components/TopBar.svelte';
  import EntryList from './components/EntryList.svelte';
  import Reader from './components/Reader.svelte';

  let user = $state(null);
  let bootError = $state(null);

  onMount(async () => {
    try {
      user = await api.me();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = '/auth/login';
        return;
      }
      bootError = err.message;
    }
  });

  // Derive the list configuration from the current route.
  const listConfig = $derived.by(() => {
    switch (route.name) {
      case 'home':       return { kind: 'entries', params: {} };
      case 'favorites':  return { kind: 'entries', params: { favorited: 1 } };
      case 'kindle':     return { kind: 'entries', params: { sent_to_kindle: 1 } };
      case 'feed':       return { kind: 'entries', params: { feed_id: route.params.id } };
      case 'folder':     return { kind: 'entries', params: { folder: route.params.name } };
      case 'pinned':     return { kind: 'pinned', params: {} };
      default:           return { kind: 'entries', params: {} };
    }
  });

  const title = $derived.by(() => {
    switch (route.name) {
      case 'home':       return 'Home';
      case 'favorites':  return 'Favorites';
      case 'pinned':     return 'Pinned';
      case 'kindle':     return 'Sent to Kindle';
      case 'feed':       return `Feed ${route.params.id}`;
      case 'folder':     return route.params.name;
      case 'entry':      return '';
      default:           return '';
    }
  });

  const isReader = $derived(route.name === 'entry');
</script>

{#if bootError}
  <p class="boot-error">{bootError}</p>
{:else if !user}
  <p class="boot">Loading…</p>
{:else}
  <TopBar {title} onBack={isReader ? back : null} />

  {#if isReader}
    {#key route.params.id}
      <Reader entryId={route.params.id} />
    {/key}
  {:else}
    {#key `${listConfig.kind}:${JSON.stringify(listConfig.params)}`}
      <EntryList kind={listConfig.kind} params={listConfig.params} />
    {/key}
  {/if}
{/if}

<style>
  .boot, .boot-error {
    padding: 2em;
    text-align: center;
  }
  .boot-error { color: #800; }
</style>
