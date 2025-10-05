<script>
  import { onMount } from 'svelte';
  import { selectedStory, selectedCluster, mapInstance, currentZoom } from '../stores.js';
  import StoryPopup from './StoryPopup.svelte';
  import ClusterPopup from './ClusterPopup.svelte';

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
  const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  let mapContainer;
  let map;
  let markers = [];
  let currentPopup = null;
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
      const data = await response.json();

      // Clear existing markers
      clearMarkers();

      if (zoom < 17) {
        // Show clusters (dynamic clustering handles zoom 1-16)
        renderClusters(data.clusters);
      } else {
        // Show individual locations (zoom 17+)
        renderLocations(data.locations);
      }
    } catch (error) {
      console.error('Error loading locations:', error);
    }
  }

  function renderClusters(clusters) {
    if (!clusters || clusters.length === 0) {
      console.log('[MapView] No clusters to render');
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

  function createStoryMarkerContent() {
    const div = document.createElement('div');
    div.style.width = '20px';
    div.style.height = '20px';
    div.style.borderRadius = '50%';
    div.style.backgroundColor = '#ff6b35';
    div.style.border = '2px solid white';
    div.style.cursor = 'pointer';
    return div;
  }

  function createClusterMarkerContent(count) {
    const div = document.createElement('div');
    div.style.width = '40px';
    div.style.height = '40px';
    div.style.borderRadius = '50%';
    div.style.backgroundColor = '#4a90e2';
    div.style.border = '3px solid white';
    div.style.display = 'flex';
    div.style.alignItems = 'center';
    div.style.justifyContent = 'center';
    div.style.color = 'white';
    div.style.fontWeight = 'bold';
    div.style.fontSize = '14px';
    div.style.cursor = 'pointer';
    div.textContent = count;
    return div;
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
      marker.setMap(null);
    });
    markers = [];
  }

  function getDarkMapStyles() {
    // Google Maps dark theme
    return [
      { elementType: 'geometry', stylers: [{ color: '#212121' }] },
      { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
      { elementType: 'labels.text.fill', stylers: [{ color: '#757575' }] },
      { elementType: 'labels.text.stroke', stylers: [{ color: '#212121' }] },
      {
        featureType: 'administrative',
        elementType: 'geometry',
        stylers: [{ color: '#757575' }],
      },
      {
        featureType: 'administrative.country',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#9e9e9e' }],
      },
      {
        featureType: 'administrative.locality',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#bdbdbd' }],
      },
      {
        featureType: 'poi',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#757575' }],
      },
      {
        featureType: 'poi.park',
        elementType: 'geometry',
        stylers: [{ color: '#181818' }],
      },
      {
        featureType: 'poi.park',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#616161' }],
      },
      {
        featureType: 'poi.park',
        elementType: 'labels.text.stroke',
        stylers: [{ color: '#1b1b1b' }],
      },
      {
        featureType: 'road',
        elementType: 'geometry.fill',
        stylers: [{ color: '#2c2c2c' }],
      },
      {
        featureType: 'road',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#8a8a8a' }],
      },
      {
        featureType: 'road.arterial',
        elementType: 'geometry',
        stylers: [{ color: '#373737' }],
      },
      {
        featureType: 'road.highway',
        elementType: 'geometry',
        stylers: [{ color: '#3c3c3c' }],
      },
      {
        featureType: 'road.highway.controlled_access',
        elementType: 'geometry',
        stylers: [{ color: '#4e4e4e' }],
      },
      {
        featureType: 'road.local',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#616161' }],
      },
      {
        featureType: 'transit',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#757575' }],
      },
      {
        featureType: 'water',
        elementType: 'geometry',
        stylers: [{ color: '#000000' }],
      },
      {
        featureType: 'water',
        elementType: 'labels.text.fill',
        stylers: [{ color: '#3d3d3d' }],
      },
    ];
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
