// Svelte stores for global state management
import { writable } from 'svelte/store';

// Currently selected story
export const selectedStory = writable(null);

// Currently selected cluster
export const selectedCluster = writable(null);

// Map instance reference
export const mapInstance = writable(null);

// Current zoom level
export const currentZoom = writable(10);
