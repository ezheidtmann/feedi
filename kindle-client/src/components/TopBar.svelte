<script>
  let { title = '', onBack = null } = $props();
</script>

<header>
  <div class="left">
    {#if onBack}
      <button class="back" onclick={onBack} aria-label="Back">‹ Back</button>
    {:else}
      <nav>
        <a href="#/">Home</a>
        <a href="#/favorites">Favorites</a>
        <a href="#/pinned">Pinned</a>
      </nav>
    {/if}
  </div>
  <div class="title">{title}</div>
</header>

<style>
  header {
    display: flex;
    align-items: center;
    gap: 1em;
    padding: 0.4em 0.8em;
    border-bottom: 1px solid #000;
    background: #fff;
    height: 2.4em;
    box-sizing: border-box;
  }
  .left {
    flex: 0 0 auto;
  }
  nav {
    display: flex;
    gap: 1em;
  }
  nav a {
    color: #000;
    text-decoration: none;
    padding: 0.2em 0;
  }
  .title {
    flex: 1 1 auto;
    text-align: right;
    font-size: 0.95em;
    color: #444;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .back {
    border: none;
    background: transparent;
    padding: 0.2em 0.4em;
    font-size: 1em;
  }
</style>
