<script>
  import { createEventDispatcher } from 'svelte';
  import { selectedStory } from '../stores.js';

  export let story;

  const dispatch = createEventDispatcher();

  function viewDetails() {
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

    <h3>{story.title}</h3>
    {#if story.date}
      <p class="date">{story.date}</p>
    {/if}
    <p class="summary">{story.summary_preview}</p>

    <button class="view-details-btn" on:click={viewDetails}>
      View Details
    </button>
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
    margin: 0 0 12px 0;
  }

  .summary {
    color: #ccc;
    font-size: 14px;
    line-height: 1.6;
    margin: 0 0 16px 0;
  }

  .view-details-btn {
    background: #0071e3;
    border: none;
    border-radius: 8px;
    color: white;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    width: 100%;
  }

  .view-details-btn:hover {
    background: #0077ed;
  }
</style>
