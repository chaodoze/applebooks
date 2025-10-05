<script>
  import { createEventDispatcher } from 'svelte';
  import { selectedCluster, selectedStory } from '../stores.js';

  export let cluster;

  const dispatch = createEventDispatcher();

  function viewStories() {
    selectedCluster.set(cluster);
    dispatch('close');
  }

  function selectStory(story) {
    selectedStory.set(story);
    dispatch('close');
  }

  function close() {
    dispatch('close');
  }
</script>

<div class="popup-overlay" on:click={close}>
  <div class="popup" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>

    <div class="count-badge">{cluster.story_count} stories</div>

    <p class="summary">{cluster.summary}</p>

    {#if cluster.date_range}
      <p class="date-range">📅 {cluster.date_range}</p>
    {/if}

    {#if cluster.key_themes && cluster.key_themes.length > 0}
      <div class="themes">
        <strong>Key themes:</strong>
        <ul>
          {#each cluster.key_themes as theme}
            <li>{theme}</li>
          {/each}
        </ul>
      </div>
    {/if}

    {#if cluster.story_count <= 4 && cluster.stories}
      <!-- For small clusters, show story list directly -->
      <div class="story-list">
        {#each cluster.stories as story (story.story_id)}
          <button class="story-card" on:click={() => selectStory(story)}>
            <h3>
              {story.title}
              {#if story.place_name}
                <span class="title-location">• {story.place_name}</span>
              {/if}
            </h3>
            {#if story.summary_preview}
              <p class="story-summary">{story.summary_preview}</p>
            {/if}
          </button>
        {/each}
      </div>
    {:else}
      <button class="view-stories-btn" on:click={viewStories}>
        View Stories
      </button>
    {/if}
  </div>
</div>

<style>
  .popup-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .popup {
    background: #2a2a2a;
    border-radius: 12px;
    padding: 24px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    position: relative;
    color: #ffffff;
  }

  .close-btn {
    position: absolute;
    top: 12px;
    right: 12px;
    background: none;
    border: none;
    color: #999;
    font-size: 32px;
    cursor: pointer;
    padding: 0;
    width: 32px;
    height: 32px;
    line-height: 1;
  }

  .close-btn:hover {
    color: #ffffff;
  }

  .count-badge {
    display: inline-block;
    background: #4a90e2;
    color: white;
    padding: 6px 12px;
    border-radius: 16px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 16px;
  }

  .summary {
    color: #e0e0e0;
    font-size: 15px;
    line-height: 1.6;
    margin: 0 0 16px 0;
  }

  .date-range {
    color: #999;
    font-size: 14px;
    margin: 0 0 16px 0;
  }

  .themes {
    background: #1a1a1a;
    border-radius: 8px;
    padding: 12px;
    margin: 0 0 16px 0;
  }

  .themes strong {
    color: #ccc;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .themes ul {
    list-style: none;
    margin: 8px 0 0 0;
    padding: 0;
  }

  .themes li {
    color: #aaa;
    font-size: 14px;
    padding: 4px 0;
  }

  .themes li::before {
    content: '•';
    color: #4a90e2;
    font-weight: bold;
    display: inline-block;
    width: 1em;
    margin-left: -1em;
    margin-right: 0.5em;
  }

  .view-stories-btn {
    background: #0071e3;
    border: none;
    border-radius: 8px;
    color: white;
    padding: 12px 24px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    width: 100%;
  }

  .view-stories-btn:hover {
    background: #0077ed;
  }

  .story-list {
    display: grid;
    gap: 12px;
    margin-top: 16px;
  }

  .story-card {
    background: #1a1a1a;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
    width: 100%;
  }

  .story-card:hover {
    background: #252525;
    border-color: #4a90e2;
  }

  .story-card h3 {
    font-size: 15px;
    font-weight: 500;
    margin: 0 0 8px 0;
    color: #ffffff;
    line-height: 1.4;
  }

  .title-location {
    color: #999;
    font-size: 13px;
    font-weight: 400;
  }

  .story-summary {
    color: #aaa;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }
</style>
