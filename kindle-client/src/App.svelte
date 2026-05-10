<script>
  import { onMount } from 'svelte';
  import { api, ApiError } from './lib/api.js';

  let state = $state({ status: 'loading', user: null, error: null });

  onMount(async () => {
    try {
      const user = await api.me();
      state.user = user;
      state.status = 'ready';
    } catch (err) {
      state.error = err instanceof ApiError && err.status === 401
        ? 'Not logged in. Visit /auth/login first.'
        : `Error: ${err.message}`;
      state.status = 'error';
    }
  });
</script>

<main>
  <h1>feedi (kindle)</h1>

  {#if state.status === 'loading'}
    <p>Loading…</p>
  {:else if state.status === 'error'}
    <p>{state.error}</p>
  {:else}
    <p>Signed in as <strong>{state.user.email}</strong>.</p>
    <p>Phase 2 scaffold. Entry list and reader coming in phase 3.</p>
  {/if}
</main>

<style>
  main {
    padding: 1em;
  }
  h1 {
    margin: 0 0 0.5em 0;
    font-size: 1.4em;
  }
</style>
