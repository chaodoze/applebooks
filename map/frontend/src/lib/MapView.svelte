<script>
  import { onMount, onDestroy } from 'svelte';
  import { selectedStory, selectedCluster, mapInstance, currentZoom } from '../stores.js';
  import StoryPopup from './StoryPopup.svelte';
  import ClusterPopup from './ClusterPopup.svelte';

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  let mapContainer;
  let map;
  let markers = [];
  let loadTimeout = null;

  // Popup component state
  let popupType = null; // 'story' or 'cluster'
  let popupData = null;
  let popupPosition = null;

  onMount(async () => {
    // Load Google Maps libraries using the global API
    const { Map } = await google.maps.importLibrary('maps');

    // Initialize map (using standard markers, not Advanced Markers)
    map = new Map(mapContainer, {
      center: { lat: 30, lng: 0 }, // Center to show all clusters globally
      zoom: 2,
      disableDefaultUI: true,
      zoomControl: true,
      fullscreenControl: true,
      gestureHandling: 'greedy',
    });

    mapInstance.set(map);

    // Listen to zoom changes
    map.addListener('zoom_changed', () => {
      const zoom = map.getZoom();
      currentZoom.set(zoom);
      loadLocations();
    });

    // Listen to bounds changes (pan/zoom) with debouncing
    map.addListener('bounds_changed', () => {
      if (loadTimeout) clearTimeout(loadTimeout);
      loadTimeout = setTimeout(() => loadLocations(), 300);
    });

    // Initial load
    loadLocations();
  });

  onDestroy(() => {
    // Clear pending debounce timer
    if (loadTimeout) {
      clearTimeout(loadTimeout);
    }
    // Clean up markers
    clearMarkers();
  });

  async function loadLocations() {
    if (!map) return;

    const bounds = map.getBounds();
    if (!bounds) return;

    const zoom = map.getZoom();
    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/locations?zoom=${zoom}&sw_lat=${sw.lat()}&sw_lon=${sw.lng()}&ne_lat=${ne.lat()}&ne_lon=${ne.lng()}`
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      // Clear existing markers
      clearMarkers();

      // Always render both clusters and individual locations
      // Backend handles the logic of when to cluster vs show individuals
      if (data.clusters && data.clusters.length > 0) {
        renderClusters(data.clusters);
      }
      if (data.locations && data.locations.length > 0) {
        renderLocations(data.locations);
      }
    } catch (error) {
      console.error('Error loading locations:', error);
      // Don't clear markers on error - keep showing last successful data
    }
  }

  function renderClusters(clusters) {
    if (!clusters || clusters.length === 0) {
      return;
    }

    console.log(`[MapView] Rendering ${clusters.length} clusters`);

    clusters.forEach(cluster => {
      try {
        const marker = new google.maps.Marker({
          position: { lat: cluster.center_lat, lng: cluster.center_lon },
          map: map,
          title: `${cluster.story_count} stories`,
          label: {
            text: String(cluster.story_count),
            color: 'white',
            fontSize: '14px',
            fontWeight: 'bold',
          },
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 20,
            fillColor: '#4a90e2',
            fillOpacity: 1,
            strokeColor: 'white',
            strokeWeight: 3,
          },
        });

        marker.addListener('click', () => {
          showClusterPopup(cluster, marker);
        });

        markers.push(marker);
        console.log(`[MapView] Created cluster marker at ${cluster.center_lat}, ${cluster.center_lon}`);
      } catch (error) {
        console.error('[MapView] Error creating cluster marker:', error, cluster);
      }
    });
  }

  function renderLocations(locations) {
    const markerElements = locations.map(location => {
      const marker = new google.maps.Marker({
        position: { lat: location.lat, lng: location.lon },
        map: map,
        title: location.title,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: '#ff6b35',
          fillOpacity: 1,
          strokeColor: 'white',
          strokeWeight: 2,
        },
      });

      marker.addListener('click', () => {
        showStoryPopup(location, marker);
      });

      return marker;
    });

    // Don't use MarkerClusterer - we handle clustering on backend
    markers = markerElements;
  }

  function showStoryPopup(story, marker) {
    popupType = 'story';
    popupData = story;
    popupPosition = marker.position;
  }

  function showClusterPopup(cluster, marker) {
    popupType = 'cluster';
    popupData = cluster;
    popupPosition = marker.position;
  }

  function closePopup() {
    popupType = null;
    popupData = null;
    popupPosition = null;
  }

  function clearMarkers() {
    markers.forEach(marker => {
      // Explicitly remove event listeners by setting map to null
      marker.setMap(null);
    });
    markers = [];
  }
</script>

<div class="map-container" bind:this={mapContainer}></div>

{#if popupType === 'story' && popupData}
  <StoryPopup story={popupData} on:close={closePopup} />
{/if}

{#if popupType === 'cluster' && popupData}
  <ClusterPopup cluster={popupData} on:close={closePopup} />
{/if}

<style>
  .map-container {
    width: 100%;
    height: 100%;
  }
</style>
