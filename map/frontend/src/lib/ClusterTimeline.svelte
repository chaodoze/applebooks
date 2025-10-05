<script>
  import { selectedCluster, selectedStory } from '../stores.js';

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  let clusterDetails = null;
  let loading = false;

  $: if ($selectedCluster) {
    loadClusterDetails($selectedCluster);
  }

  async function loadClusterDetails(cluster) {
    // For dynamic clusters, we already have the stories data
    if (cluster.cluster_id?.startsWith('dynamic_') && cluster.stories) {
      clusterDetails = cluster;
      loading = false;

      // Debug: Log date information
      const dates = cluster.stories.map(s => s.date).filter(d => d);
      console.log(`[ClusterTimeline] Cluster has ${cluster.stories.length} stories, ${dates.length} with dates`);
      if (dates.length > 0) {
        console.log('[ClusterTimeline] Sample dates:', dates.slice(0, 10));
        const years = dates.map(d => d.match(/\d{4}/)?.[0]).filter(y => y);
        if (years.length > 0) {
          console.log('[ClusterTimeline] Date range:', Math.min(...years), '-', Math.max(...years));
        }
      }

      return;
    }

    // For static clusters (if any), fetch from API
    loading = true;
    try {
      const response = await fetch(`${API_BASE_URL}/api/cluster/${cluster.cluster_id}`);
      clusterDetails = await response.json();
    } catch (error) {
      console.error('Error loading cluster details:', error);
    } finally {
      loading = false;
    }
  }

  function close() {
    selectedCluster.set(null);
    clusterDetails = null;
  }

  function selectStory(story) {
    close(); // Close cluster timeline first
    selectedStory.set(story);
  }

  // Helper to parse years from dates
  function getYear(dateStr) {
    if (!dateStr) return null;
    const match = dateStr.match(/\d{4}/);
    return match ? parseInt(match[0]) : null;
  }

  // Calculate timeline positions
  $: timelineData = clusterDetails ? calculateTimeline(clusterDetails.stories) : null;

  function calculateTimeline(stories) {
    const years = stories.map(s => getYear(s.date)).filter(y => y !== null);

    // If no dates available, return minimal timeline data
    if (years.length === 0) {
      return {
        minYear: null,
        maxYear: null,
        yearRange: 0,
        hasTimeline: false,
        datedCount: 0,
        stories: stories.map(story => ({
          ...story,
          year: null,
          position: 50,
        })),
      };
    }

    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    const yearRange = Math.max(maxYear - minYear, 1); // Ensure yearRange is at least 1

    // Map stories with their year and position
    const storiesWithTimeline = stories.map(story => {
      const storyYear = getYear(story.date);
      return {
        ...story,
        year: storyYear,
        position: storyYear ? ((storyYear - minYear) / yearRange) * 100 : 50,
      };
    });

    // Sort stories by date string (earliest first), undated stories at the end
    const sortedStories = storiesWithTimeline.sort((a, b) => {
      if (!a.date && !b.date) return 0;
      if (!a.date) return 1;  // a goes to end
      if (!b.date) return -1; // b goes to end
      // Both have dates - compare as strings (works for ISO dates like "2016-05")
      return a.date.localeCompare(b.date);
    });

    return {
      minYear,
      maxYear,
      yearRange,
      hasTimeline: true,
      datedCount: years.length,
      stories: sortedStories,
    };
  }
</script>

<div class="modal-overlay" on:click={close}>
  <div class="modal" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>

    {#if loading}
      <div class="loading">Loading...</div>
    {:else if clusterDetails && timelineData}
      <div class="header">
        <h2>
          {clusterDetails.story_count} Stories
          {#if timelineData.hasTimeline}
            <span class="dated-count">({timelineData.datedCount} with dates)</span>
          {/if}
        </h2>
        <p class="summary">{clusterDetails.summary}</p>
      </div>

      {#if timelineData.hasTimeline}
        <div class="timeline-container">
          <div class="timeline-axis">
            <div class="year-label start">{timelineData.minYear}</div>
            <div class="timeline-line"></div>
            <div class="year-label end">{timelineData.maxYear}</div>
          </div>

          <div class="stories-track">
            {#each timelineData.stories as story (story.story_id)}
              <button
                class="story-dot"
                style="left: {story.position}%"
                on:click={() => selectStory(story)}
                title={story.title}
              >
                <span class="tooltip">{story.title}</span>
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <div class="story-list">
        {#each timelineData.stories as story (story.story_id)}
          <button class="story-card" on:click={() => selectStory(story)}>
            <div class="story-header">
              <h3>{story.title}</h3>
              {#if story.date}
                <span class="date">{story.date}</span>
              {/if}
            </div>
            {#if story.summary_preview}
              <p class="story-summary">{story.summary_preview}</p>
            {:else if story.summary}
              <p class="story-summary">{story.summary.slice(0, 150)}...</p>
            {/if}
          </button>
        {/each}
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
    max-width: 900px;
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

  .header {
    margin-bottom: 32px;
  }

  h2 {
    font-size: 24px;
    font-weight: 600;
    margin: 0 0 12px 0;
    color: #4a90e2;
  }

  .dated-count {
    color: #999;
    font-size: 16px;
    font-weight: 400;
  }

  .summary {
    color: #ccc;
    font-size: 15px;
    line-height: 1.6;
    margin: 0;
  }

  .timeline-container {
    background: #1a1a1a;
    border-radius: 12px;
    padding: 40px 20px;
    margin-bottom: 32px;
  }

  .timeline-axis {
    position: relative;
    display: flex;
    align-items: center;
    margin-bottom: 40px;
  }

  .timeline-line {
    flex: 1;
    height: 2px;
    background: #4a4a4a;
    margin: 0 12px;
  }

  .year-label {
    color: #999;
    font-size: 14px;
    font-weight: 500;
  }

  .stories-track {
    position: relative;
    height: 60px;
  }

  .story-dot {
    position: absolute;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #ff6b35;
    border: 2px solid #2a2a2a;
    cursor: pointer;
    transform: translateX(-50%);
    transition: all 0.2s;
    padding: 0;
  }

  .story-dot:hover {
    width: 20px;
    height: 20px;
    background: #ff8555;
    z-index: 10;
  }

  .story-dot:hover .tooltip {
    opacity: 1;
    visibility: visible;
  }

  .tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: #1a1a1a;
    color: white;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    white-space: nowrap;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s;
    pointer-events: none;
    margin-bottom: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  .story-list {
    display: grid;
    gap: 12px;
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

  .story-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 8px;
  }

  h3 {
    font-size: 16px;
    font-weight: 500;
    margin: 0;
    color: #ffffff;
    flex: 1;
  }

  .date {
    color: #999;
    font-size: 13px;
    white-space: nowrap;
  }

  .story-summary {
    color: #aaa;
    font-size: 14px;
    line-height: 1.5;
    margin: 0;
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
