<script>
  import { createEventDispatcher, onMount } from 'svelte';

  export let story;

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
  const dispatch = createEventDispatcher();

  let fullStory = null;
  let loading = true;
  let error = null;

  onMount(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/story/${story.story_id}`);
      if (!response.ok) {
        throw new Error(`Failed to load story: ${response.statusText}`);
      }
      fullStory = await response.json();
    } catch (err) {
      console.error('Error loading story details:', err);
      error = err.message;
    } finally {
      loading = false;
    }
  });

  function close() {
    dispatch('close');
  }

  // Format location for display
  function formatLocation(story) {
    if (story.address) {
      return story.address;
    }
    if (story.place_name) {
      return story.place_name;
    }
    return null;
  }

  const location = formatLocation(story);
</script>

<div class="popup-overlay" on:click={close}>
  <div class="popup" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>

    {#if loading}
      <div class="loading-state">
        <h3>{story.title}</h3>
        {#if story.date}
          <p class="date">{story.date}</p>
        {/if}
        {#if location}
          <p class="location">📍 {location}</p>
        {/if}
        <p class="loading-text">Loading details...</p>
      </div>
    {:else if error}
      <div class="error-state">
        <h3>{story.title}</h3>
        <p class="error-text">Failed to load full details</p>
      </div>
    {:else if fullStory}
      <h3>{fullStory.title}</h3>
      {#if fullStory.parsed_date}
        <p class="date">{fullStory.parsed_date}</p>
      {/if}
      {#if location}
        <p class="location">📍 {location}</p>
      {/if}
      <p class="summary">{fullStory.summary}</p>
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
    max-width: 400px;
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

  h3 {
    margin: 0 0 8px 0;
    font-size: 18px;
    font-weight: 600;
    line-height: 1.4;
    padding-right: 32px;
  }

  .date {
    color: #999;
    font-size: 13px;
    margin: 0 0 8px 0;
  }

  .location {
    color: #999;
    font-size: 13px;
    margin: 0 0 12px 0;
    font-style: italic;
  }

  .summary {
    color: #ccc;
    font-size: 14px;
    line-height: 1.6;
    margin: 0;
  }

  .loading-text {
    color: #999;
    font-size: 13px;
    font-style: italic;
    margin: 12px 0 0 0;
  }

  .error-text {
    color: #ff6b6b;
    font-size: 13px;
    margin: 12px 0 0 0;
  }
</style>
