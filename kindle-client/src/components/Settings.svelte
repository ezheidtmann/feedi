<script>
  import { settings, FONT_SIZE_OPTIONS, setFontSize, setHideSeen } from '../lib/settings.svelte.js';
</script>

<div class="settings">
  <section>
    <h2>Font size</h2>
    <div class="options">
      {#each FONT_SIZE_OPTIONS as opt}
        <label>
          <input
            type="radio"
            name="font-size"
            value={opt.value}
            checked={settings.fontSize === opt.value}
            onchange={() => setFontSize(opt.value)}
          />
          {opt.label}
        </label>
      {/each}
    </div>
  </section>

  <section>
    <h2>Reading</h2>
    <label class="toggle">
      <input
        type="checkbox"
        checked={settings.hideSeen}
        onchange={(e) => setHideSeen(e.target.checked)}
      />
      Hide entries already seen
    </label>
    <p class="hint">When off, viewed entries stay in the home and folder lists.</p>
  </section>
</div>

<style>
  .settings {
    padding: 1em;
    overflow-y: auto;
    height: calc(100vh - 2.4em);
    box-sizing: border-box;
  }
  section {
    margin-bottom: 1.5em;
  }
  h2 {
    font-size: 1em;
    margin: 0 0 0.4em 0;
    border-bottom: 1px solid #000;
    padding-bottom: 0.2em;
  }
  .options {
    display: flex;
    flex-direction: column;
    gap: 0.4em;
  }
  label {
    display: flex;
    align-items: center;
    gap: 0.6em;
    padding: 0.3em 0;
    font-size: 1em;
  }
  input[type="radio"], input[type="checkbox"] {
    width: 1.2em;
    height: 1.2em;
  }
  .hint {
    margin: 0.3em 0 0 1.8em;
    color: #555;
    font-size: 0.85em;
  }
</style>
