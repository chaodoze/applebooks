<script>
  import MapView from './lib/MapView.svelte';
  import StoryModal from './lib/StoryModal.svelte';
  import ClusterTimeline from './lib/ClusterTimeline.svelte';
  import { selectedStory, selectedCluster } from './stores.js';

  // Ensure only one modal is open at a time
  $: if ($selectedStory && $selectedCluster) {
    selectedCluster.set(null);
  }
</script>

<main>
  <MapView />

  {#if $selectedStory}
    <StoryModal />
  {/if}

  {#if $selectedCluster}
    <ClusterTimeline />
  {/if}
</main>

<style>
  main {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
  }
</style>
