<script>
  import { onDestroy } from 'svelte';
  import { selectedStory } from '../stores.js';

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

  let storyDetails = null;
  let loading = true;
  let error = null;
  let abortController = null;

  $: if ($selectedStory) {
    loadStoryDetails($selectedStory.story_id);
  }

  async function loadStoryDetails(storyId) {
    // Cancel previous request if any
    if (abortController) {
      abortController.abort();
    }

    abortController = new AbortController();
    loading = true;
    error = null;

    try {
      const response = await fetch(`${API_BASE_URL}/api/story/${storyId}`, {
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`Failed to load story: ${response.statusText}`);
      }

      storyDetails = await response.json();
    } catch (err) {
      if (err.name === 'AbortError') {
        // Request was cancelled, ignore
        return;
      }
      console.error('Error loading story details:', err);
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function close() {
    if (abortController) {
      abortController.abort();
    }
    selectedStory.set(null);
    storyDetails = null;
    error = null;
  }

  onDestroy(() => {
    if (abortController) {
      abortController.abort();
    }
  });
</script>

<div class="modal-overlay" on:click={close}>
  <div class="modal" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>

    {#if loading}
      <div class="loading">Loading...</div>
    {:else if error}
      <div class="error">
        <p>Failed to load story details</p>
        <p class="error-message">{error}</p>
      </div>
    {:else if storyDetails}
      <div class="content">
        <h1>{storyDetails.title}</h1>

        {#if storyDetails.parsed_date}
          <p class="date">{storyDetails.parsed_date}</p>
        {/if}

        <div class="summary">
          <p>{storyDetails.summary}</p>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2000;
    padding: 20px;
  }

  .modal {
    background: #2a2a2a;
    border-radius: 16px;
    padding: 40px;
    max-width: 700px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 16px 64px rgba(0, 0, 0, 0.5);
    position: relative;
    color: #ffffff;
  }

  .close-btn {
    position: absolute;
    top: 16px;
    right: 16px;
    background: none;
    border: none;
    color: #999;
    font-size: 40px;
    cursor: pointer;
    padding: 0;
    width: 40px;
    height: 40px;
    line-height: 1;
    transition: color 0.2s;
  }

  .close-btn:hover {
    color: #ffffff;
  }

  .loading {
    text-align: center;
    color: #999;
    padding: 60px 20px;
    font-size: 16px;
  }

  .error {
    text-align: center;
    color: #ff6b6b;
    padding: 60px 20px;
  }

  .error p {
    margin: 0 0 8px 0;
    font-size: 16px;
    font-weight: 600;
  }

  .error-message {
    color: #999;
    font-size: 14px;
    font-weight: 400;
  }

  .content {
    padding-right: 40px;
  }

  h1 {
    font-size: 28px;
    font-weight: 600;
    line-height: 1.3;
    margin: 0 0 12px 0;
    color: #ffffff;
  }

  .date {
    color: #999;
    font-size: 14px;
    margin: 0 0 24px 0;
  }

  .summary {
    color: #e0e0e0;
    font-size: 16px;
    line-height: 1.7;
  }

  .summary p {
    margin: 0 0 16px 0;
  }

  /* Scrollbar styling */
  .modal::-webkit-scrollbar {
    width: 8px;
  }

  .modal::-webkit-scrollbar-track {
    background: #1a1a1a;
    border-radius: 8px;
  }

  .modal::-webkit-scrollbar-thumb {
    background: #4a4a4a;
    border-radius: 8px;
  }

  .modal::-webkit-scrollbar-thumb:hover {
    background: #5a5a5a;
  }
</style>
