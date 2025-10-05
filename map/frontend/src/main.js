import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// Validate required environment variables
const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

if (!GOOGLE_MAPS_API_KEY) {
  console.error('ERROR: VITE_GOOGLE_MAPS_API_KEY is not set');
  console.error('Please add VITE_GOOGLE_MAPS_API_KEY to your .env file');
  document.getElementById('app').innerHTML = `
    <div style="padding: 40px; text-align: center; color: #ff6b6b; font-family: system-ui;">
      <h1>Configuration Error</h1>
      <p>Google Maps API key is missing. Please check your environment configuration.</p>
    </div>
  `;
  throw new Error('Missing VITE_GOOGLE_MAPS_API_KEY environment variable');
}

console.log(`[Config] API Base URL: ${API_BASE_URL}`);

// Initialize Google Maps bootstrap loader
(g=>{var h,a,k,p="The Google Maps JavaScript API",c="google",l="importLibrary",q="__ib__",m=document,b=window;b=b[c]||(b[c]={});var d=b.maps||(b.maps={}),r=new Set,e=new URLSearchParams,u=()=>h||(h=new Promise(async(f,n)=>{await (a=m.createElement("script"));e.set("libraries",[...r]+"");for(k in g)e.set(k.replace(/[A-Z]/g,t=>"_"+t[0].toLowerCase()),g[k]);e.set("callback",c+".maps."+q);a.src=`https://maps.${c}apis.com/maps/api/js?`+e;d[q]=f;a.onerror=()=>h=n(Error(p+" could not load."));a.nonce=m.querySelector("script[nonce]")?.nonce||"";m.head.append(a)}));d[l]?console.warn(p+" only loads once. Ignoring:",g):d[l]=(f,...n)=>r.add(f)&&u().then(()=>d[l](f,...n))})({
  key: GOOGLE_MAPS_API_KEY,
  v: "weekly",
});

const app = mount(App, {
  target: document.getElementById('app'),
})

export default app
