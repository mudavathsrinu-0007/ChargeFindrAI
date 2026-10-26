// ============================================================================
// CHARGEFINDR AI — FRONTEND CONTROLLER & GOOGLE MAPS INTEGRATION
// ============================================================================

// Determine API base URL dynamically
const API_BASE = (window.location.origin && window.location.origin.includes(":5000")) 
  ? "" 
  : "http://127.0.0.1:5000";

// ============================================================================
// GOOGLE MAPS CONFIGURATION
// To enable interactive Google Maps and road routing:
// 1. Replace the placeholder string below with your Google Cloud Maps API Key.
// 2. In Google Cloud Console, restrict the key by HTTP Referrer:
//    http://127.0.0.1:5000/* and http://localhost:5000/*
// 3. Enable the "Maps JavaScript API" (and optionally "Directions API" for routing).
// Safety: If the key is left as placeholder, the dashboard continues working 100%.
// ============================================================================
const GOOGLE_MAPS_API_KEY = "YOUR_GOOGLE_MAPS_API_KEY";

// DOM Elements - General
const statusDot = document.getElementById("status-indicator");
const statusText = document.getElementById("status-text");
const recommendForm = document.getElementById("recommend-form");
const locationSelect = document.getElementById("location-select");
const chargerTypeSelect = document.getElementById("charger-type-select");
const prioritySelect = document.getElementById("priority-select");
const btnShowAll = document.getElementById("btn-show-all");
const recommendList = document.getElementById("recommend-list");
const recommendLoading = document.getElementById("recommend-loading");
const recommendError = document.getElementById("recommend-error");
const recommendCountBadge = document.getElementById("recommend-count-badge");
const alertBanner = document.getElementById("alert-banner");
const alertMessage = document.getElementById("alert-message");

// DOM Elements - Demand Prediction
const demandHourSelect = document.getElementById("demand-hour");
const demandDaySelect = document.getElementById("demand-day");
const btnPredictDemand = document.getElementById("btn-predict-demand");
const demandKwh = document.getElementById("demand-kwh");
const demandLevelBadge = document.getElementById("demand-level-badge");
const modelName = document.getElementById("model-name");
const demandAdvisory = document.getElementById("demand-advisory");
const hourlyChart = document.getElementById("hourly-chart");
const metricMae = document.getElementById("metric-mae");
const metricRmse = document.getElementById("metric-rmse");
const metricSplit = document.getElementById("metric-split");
const metricTrainRecords = document.getElementById("metric-train-records");
const modelDatasetBadge = document.getElementById("model-dataset-badge");

// DOM Elements - Table
const stationsTableBody = document.getElementById("stations-table-body");

// DOM Elements - Google Maps
const mapContainer = document.getElementById("map");
const mapFallbackBanner = document.getElementById("map-fallback-banner");
const btnUseLocation = document.getElementById("btn-use-location");
const routingSummaryBox = document.getElementById("routing-summary-box");
const routeDestinationName = document.getElementById("route-destination-name");
const routeMetrics = document.getElementById("route-metrics");
const btnClearRoute = document.getElementById("btn-clear-route");

// Map State Variables
let googleMap = null;
let stationMarkers = {};
let infoWindow = null;
let userMarker = null;
let userCoords = null;
let directionsService = null;
let directionsRenderer = null;
let allStationsData = [];
let selectedStationForRoute = null;

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  populateHourDropdown();
  setupEventListeners();
  initMapLoader();
  checkBackendHealth();
  fetchStationLocations();
  fetchAllStations();
  fetchRecommendations();
  fetchDemandPrediction();
  initAuthSystem();
});

function populateHourDropdown() {
  const currentHour = new Date().getHours();
  demandHourSelect.innerHTML = "";
  for (let h = 0; h < 24; h++) {
    const opt = document.createElement("option");
    opt.value = h;
    const formatted = `${String(h).padStart(2, "0")}:00`;
    opt.textContent = formatted;
    if (h === currentHour) opt.selected = true;
    demandHourSelect.appendChild(opt);
  }

  // Set current day of week (0=Mon ... 6=Sun)
  let dow = new Date().getDay() - 1;
  if (dow < 0) dow = 6;
  if (demandDaySelect) demandDaySelect.value = String(dow);
}

function setupEventListeners() {
  recommendForm.addEventListener("submit", (e) => {
    e.preventDefault();
    fetchRecommendations();
  });

  btnShowAll.addEventListener("click", () => {
    locationSelect.value = "Any";
    chargerTypeSelect.value = "Any";
    prioritySelect.value = "balanced";
    fetchRecommendations();
  });

  btnPredictDemand.addEventListener("click", () => {
    fetchDemandPrediction();
  });

  if (btnUseLocation) {
    btnUseLocation.addEventListener("click", () => {
      handleUserGeolocation();
    });
  }

  if (btnClearRoute) {
    btnClearRoute.addEventListener("click", () => {
      clearActiveRoute();
    });
  }
}

// ============================================================================
// 1. GOOGLE MAPS INTEGRATION & MARKERS
// ============================================================================
function initMapLoader() {
  // Check if API key is still placeholder or absent
  if (!GOOGLE_MAPS_API_KEY || GOOGLE_MAPS_API_KEY === "YOUR_GOOGLE_MAPS_API_KEY") {
    console.info("[ChargeFindr AI] Google Maps API key placeholder detected. Displaying setup guidance.");
    if (mapFallbackBanner) mapFallbackBanner.style.display = "flex";
    if (mapContainer) {
      mapContainer.innerHTML = `
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:#94a3b8; text-align:center; padding:1.5rem;">
          <span style="font-size:2.5rem; margin-bottom:0.5rem;">🗺️</span>
          <strong style="color:#f8fafc; font-size:1.05rem;">Google Maps Standby Mode</strong>
          <p style="font-size:0.85rem; max-width:480px; margin-top:0.4rem;">
            To render the interactive satellite/street map and road routing, add your restricted Google Maps API key in <code>frontend/script.js</code>.
          </p>
          <span style="margin-top:0.75rem; font-size:0.78rem; color:#10b981; background:rgba(16,185,129,0.1); padding:0.3rem 0.75rem; border-radius:9999px;">
            ✓ All other backend APIs, recommendations, and ML demand features are active.
          </span>
        </div>
      `;
    }
    return;
  }

  // Load Google Maps JavaScript API dynamically with callback
  window.initGoogleMap = initGoogleMap;
  window.gm_authFailure = () => {
    console.warn("[ChargeFindr AI] Google Maps authentication failed. Showing setup banner.");
    if (mapFallbackBanner) mapFallbackBanner.style.display = "flex";
  };

  const script = document.createElement("script");
  script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_API_KEY)}&callback=initGoogleMap&loading=async`;
  script.async = true;
  script.defer = true;
  document.head.appendChild(script);
}

function initGoogleMap() {
  if (mapFallbackBanner) mapFallbackBanner.style.display = "none";
  if (!mapContainer) return;

  // Center on West Hyderabad EV Hub (Madhapur / Hitech City / Kondapur area)
  const hyderabadCenter = { lat: 17.4450, lng: 78.3750 };

  const darkMapStyle = [
    { elementType: "geometry", stylers: [{ color: "#1e293b" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#0f172a" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#94a3b8" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#334155" }] },
    { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#1e293b" }] },
    { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#cbd5e1" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#0f172a" }] },
    { featureType: "poi", elementType: "labels.text.fill", stylers: [{ color: "#64748b" }] }
  ];

  googleMap = new google.maps.Map(mapContainer, {
    center: hyderabadCenter,
    zoom: 12,
    styles: darkMapStyle,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true
  });

  infoWindow = new google.maps.InfoWindow();

  if (google.maps.DirectionsService) {
    directionsService = new google.maps.DirectionsService();
    directionsRenderer = new google.maps.DirectionsRenderer({
      map: googleMap,
      suppressMarkers: false,
      polylineOptions: {
        strokeColor: "#10b981",
        strokeWeight: 5,
        strokeOpacity: 0.85
      }
    });
  }

  // Plot markers if station data already loaded
  if (allStationsData.length > 0) {
    plotStationMarkers(allStationsData);
  }
}

function plotStationMarkers(stations) {
  if (!googleMap) return;

  // Clear previous markers
  Object.values(stationMarkers).forEach(m => m.setMap(null));
  stationMarkers = {};

  const bounds = new google.maps.LatLngBounds();
  let validMarkerCount = 0;

  stations.forEach(station => {
    if (station.latitude == null || station.longitude == null) return;

    const pos = { lat: Number(station.latitude), lng: Number(station.longitude) };
    bounds.extend(pos);
    validMarkerCount++;

    const isAvailable = station.available_ports > 0;
    const pinColor = isAvailable ? "#10b981" : "#ef4444";

    // Custom SVG Marker Icon
    const markerSvg = {
      path: "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z",
      fillColor: pinColor,
      fillOpacity: 1,
      strokeWeight: 1.5,
      strokeColor: "#ffffff",
      scale: 1.6,
      anchor: new google.maps.Point(12, 22)
    };

    const marker = new google.maps.Marker({
      position: pos,
      map: googleMap,
      title: station.station_name,
      icon: markerSvg,
      animation: google.maps.Animation.DROP
    });

    marker.addListener("click", () => {
      openStationInfoWindow(station, marker);
    });

    stationMarkers[station.station_id] = marker;
  });

  if (validMarkerCount > 1) {
    googleMap.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
  }
}

function openStationInfoWindow(station, marker) {
  if (!infoWindow || !googleMap) return;

  const isAvail = station.available_ports > 0;
  const statusColor = isAvail ? "#10b981" : "#ef4444";
  const statusText = isAvail ? `● ${station.available_ports}/${station.total_ports} Ports Available` : `✕ Congested (0 Ports)`;

  const contentString = `
    <div class="map-iw-content">
      <div class="map-iw-header">
        <strong>${escapeHtml(station.station_name)}</strong>
        <span style="font-size:0.75rem; color:${statusColor}; font-weight:600;">${statusText}</span>
      </div>
      <div class="map-iw-meta">
        <div><strong>Locality:</strong> ${escapeHtml(station.location)}</div>
        <div><strong>Charger:</strong> ${escapeHtml(station.charger_type)} (${station.capacity_kw} kW)</div>
        <div><strong>Est. Queue:</strong> ${station.estimated_wait_minutes} mins | <strong>Demand:</strong> ${station.demand_level}</div>
        <div style="font-size:0.7rem; color:#94a3b8; margin-top:3px;">
          <em>Demonstration station with verified locality coordinates (${Number(station.latitude).toFixed(4)}, ${Number(station.longitude).toFixed(4)})</em>
        </div>
      </div>
      <div class="map-iw-actions">
        <button class="btn-card-map" onclick="requestRouteToStation(${station.station_id})">
          🚗 Route Here
        </button>
      </div>
    </div>
  `;

  infoWindow.setContent(contentString);
  infoWindow.open(googleMap, marker);
}

// Window-scoped function for InfoWindow route button
window.requestRouteToStation = function(stationId) {
  const station = allStationsData.find(s => s.station_id === stationId);
  if (!station) return;
  selectedStationForRoute = station;

  if (!userCoords) {
    handleUserGeolocation(station);
  } else {
    calculateRoadRoute(userCoords, station);
  }
};

window.focusStationOnMap = function(stationId) {
  const marker = stationMarkers[stationId];
  const station = allStationsData.find(s => s.station_id === stationId);
  if (!googleMap || !marker || !station) {
    if (mapContainer) mapContainer.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }

  googleMap.panTo(marker.getPosition());
  googleMap.setZoom(14);
  marker.setAnimation(google.maps.Animation.BOUNCE);
  setTimeout(() => marker.setAnimation(null), 1400);
  openStationInfoWindow(station, marker);
  mapContainer.scrollIntoView({ behavior: "smooth", block: "center" });
};

// Geolocation Handler
function handleUserGeolocation(targetStationAfter = null) {
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }

  btnUseLocation.disabled = true;
  btnUseLocation.textContent = "📍 Locating...";

  navigator.geolocation.getCurrentPosition(
    (position) => {
      userCoords = {
        lat: position.coords.latitude,
        lng: position.coords.longitude
      };

      btnUseLocation.disabled = false;
      btnUseLocation.textContent = "📍 Location Active";
      btnUseLocation.classList.add("btn-primary");
      btnUseLocation.classList.remove("btn-secondary");

      if (googleMap) {
        if (userMarker) userMarker.setMap(null);

        userMarker = new google.maps.Marker({
          position: userCoords,
          map: googleMap,
          title: "Your Location",
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            fillColor: "#0ea5e9",
            fillOpacity: 1,
            strokeColor: "#ffffff",
            strokeWeight: 2,
            scale: 7
          }
        });

        googleMap.panTo(userCoords);
      }

      if (targetStationAfter) {
        calculateRoadRoute(userCoords, targetStationAfter);
      } else if (selectedStationForRoute) {
        calculateRoadRoute(userCoords, selectedStationForRoute);
      }
    },
    (err) => {
      btnUseLocation.disabled = false;
      btnUseLocation.textContent = "📍 Use My Location";
      console.warn(`[Geolocation] Permission denied or unavailable: ${err.message}`);
      alert("Browser location permission was not granted. The map remains centered on Hyderabad charging stations.");
    },
    { timeout: 10000, enableHighAccuracy: true }
  );
}

// Road Route Calculation via Google DirectionsService
function calculateRoadRoute(origin, station) {
  if (!directionsService || !directionsRenderer) {
    alert("Google Directions Service is not available. Please verify Directions API is enabled on your API key.");
    return;
  }

  const destCoords = { lat: Number(station.latitude), lng: Number(station.longitude) };

  directionsService.route(
    {
      origin: origin,
      destination: destCoords,
      travelMode: google.maps.TravelMode.DRIVING
    },
    (result, status) => {
      if (status === google.maps.DirectionsStatus.OK) {
        directionsRenderer.setDirections(result);
        const leg = result.routes[0].legs[0];

        if (routingSummaryBox) {
          routingSummaryBox.style.display = "flex";
          routeDestinationName.textContent = `Route to ${station.station_name} (${station.location})`;
          routeMetrics.textContent = `Actual Road Distance: ${leg.distance.text} | Est. Travel Duration: ${leg.duration.text} (via Google Directions)`;
        }
      } else {
        console.warn(`[DirectionsService] Failed: ${status}`);
        alert(`Could not calculate road directions to ${station.station_name}: ${status}`);
      }
    }
  );
}

function clearActiveRoute() {
  if (directionsRenderer) directionsRenderer.set("directions", null);
  if (routingSummaryBox) routingSummaryBox.style.display = "none";
  selectedStationForRoute = null;
}

// Synchronize #1 recommendation with map
function highlightTopRecommendationOnMap(recommendations) {
  if (!googleMap || !recommendations || !recommendations.length) return;
  const top = recommendations[0];
  const marker = stationMarkers[top.station_id];
  if (marker) {
    marker.setAnimation(google.maps.Animation.BOUNCE);
    setTimeout(() => marker.setAnimation(null), 1400);
  }
}

// ============================================================================
// 2. HEALTH CHECK & DATABASE STATIONS (MODULES 5 & 7)
// ============================================================================
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) throw new Error("Health check returned non-200");
    const data = await res.json();
    if (data.status === "healthy" && data.database === "connected") {
      statusDot.className = "status-dot online";
      statusText.textContent = "Backend & MySQL Connected";
    } else {
      statusDot.className = "status-dot offline";
      statusText.textContent = "Database Disconnected";
    }
  } catch (err) {
    statusDot.className = "status-dot offline";
    statusText.textContent = "Backend Offline (Port 5000)";
  }
}

async function fetchAllStations() {
  try {
    const res = await fetch(`${API_BASE}/api/stations`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    allStationsData = json.data || [];
    renderDatabaseTable(allStationsData);
    fetchCongestionAlerts();

    // Plot markers if map is initialized
    if (googleMap) {
      plotStationMarkers(allStationsData);
    }
  } catch (err) {
    stationsTableBody.innerHTML = `<tr><td colspan="10" class="text-center" style="color: #fca5a5;">Failed to load stations: ${err.message}</td></tr>`;
  }
}

// Fetch Distinct Locations from Database (Database-Driven Dropdown)
async function fetchStationLocations() {
  try {
    const res = await fetch(`${API_BASE}/api/stations/locations`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const locations = json.data || [];
    populateLocationDropdown(locations);
  } catch (err) {
    console.warn(`[ChargeFindr AI] Failed to fetch station locations: ${err.message}`);
    // Safe error state without hardcoded fallback locations
    locationSelect.innerHTML = `<option value="Any">All Hyderabad Areas</option><option value="" disabled>(Locations unavailable - DB offline)</option>`;
  }
}

function populateLocationDropdown(locations) {
  // Always preserve "All Hyderabad Areas" as the first and default option
  const currentVal = locationSelect.value || "Any";
  locationSelect.innerHTML = `<option value="Any">All Hyderabad Areas</option>`;

  if (!locations || !locations.length) {
    const emptyOpt = document.createElement("option");
    emptyOpt.value = "";
    emptyOpt.disabled = true;
    emptyOpt.textContent = "(No locations found in database)";
    locationSelect.appendChild(emptyOpt);
    return;
  }

  // Prevent duplicates using a Set
  const uniqueLocations = Array.from(new Set(locations.map(loc => String(loc).trim()).filter(Boolean)));

  uniqueLocations.forEach(loc => {
    const opt = document.createElement("option");
    opt.value = loc;
    opt.textContent = loc;
    if (loc === currentVal) {
      opt.selected = true;
    }
    locationSelect.appendChild(opt);
  });
}

function renderDatabaseTable(stations) {
  if (!stations.length) {
    stationsTableBody.innerHTML = `<tr><td colspan="10" class="text-center">No stations found in database.</td></tr>`;
    return;
  }

  stationsTableBody.innerHTML = stations.map(s => {
    const isAvail = s.available_ports > 0;
    const statusBadge = isAvail 
      ? `<span class="badge badge-success">Available</span>` 
      : `<span class="badge badge-danger">Full / Wait</span>`;
    
    const demandBadge = s.demand_level.toLowerCase() === "low"
      ? `<span class="badge badge-success">Low</span>`
      : s.demand_level.toLowerCase() === "medium"
        ? `<span class="badge badge-warning">Medium</span>`
        : `<span class="badge badge-danger">High</span>`;

    return `
      <tr>
        <td><strong>#${s.station_id}</strong></td>
        <td><strong>${escapeHtml(s.station_name)}</strong></td>
        <td>${escapeHtml(s.location)}</td>
        <td>${s.distance_km} km <small style="color: var(--text-dim)">(sample)</small></td>
        <td>${escapeHtml(s.charger_type)}</td>
        <td>${s.capacity_kw} kW</td>
        <td><strong>${s.available_ports}</strong> / ${s.total_ports}</td>
        <td>${s.estimated_wait_minutes} mins</td>
        <td>${demandBadge}</td>
        <td>${statusBadge}</td>
      </tr>
    `;
  }).join("");
}

// Smart Congestion Notification (Module 6) — Backend API Driven
let isFetchingAlerts = false;

async function fetchCongestionAlerts() {
  if (isFetchingAlerts) return;
  isFetchingAlerts = true;

  try {
    const res = await fetch(`${API_BASE}/api/stations/alerts`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.success && data.has_alert && Array.isArray(data.alerts) && data.alerts.length > 0) {
      const topAlert = data.alerts[0];
      const congested = topAlert.congested_station;
      const alt = topAlert.recommended_alternative;

      if (alertBanner && alertMessage) {
        alertBanner.style.display = "flex";
        if (alt) {
          alertMessage.innerHTML = `<strong>Smart Alert:</strong> <em>${escapeHtml(congested.station_name)}</em> (${escapeHtml(congested.location)}) is currently congested (${congested.available_ports} ports available, ${congested.estimated_wait_minutes} min wait). Recommend re-routing to <strong>${escapeHtml(alt.station_name)}</strong> (~${alt.estimated_wait_minutes} min wait).`;
        } else {
          alertMessage.innerHTML = `<strong>Smart Alert:</strong> <em>${escapeHtml(congested.station_name)}</em> (${escapeHtml(congested.location)}) is currently congested (${congested.available_ports} ports available, ${congested.estimated_wait_minutes} min wait). No low-wait alternatives currently available.`;
        }
      }
    } else {
      if (alertBanner) alertBanner.style.display = "none";
    }
  } catch (err) {
    console.warn(`[ChargeFindr AI] Failed to fetch station alerts: ${err.message}`);
    if (alertBanner) alertBanner.style.display = "none";
  } finally {
    isFetchingAlerts = false;
  }
}

// Retain alias for compatibility
const checkCongestionAlerts = fetchCongestionAlerts;

// ============================================================================
// 3. RECOMMENDATION API CALL (MODULES 1 & 3)
// ============================================================================
async function fetchRecommendations() {
  recommendLoading.style.display = "flex";
  recommendError.style.display = "none";
  recommendList.innerHTML = "";

  const payload = {
    location: locationSelect.value,
    charger_type: chargerTypeSelect.value,
    priority: prioritySelect.value
  };

  try {
    const res = await fetch(`${API_BASE}/api/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const data = json.data;

    recommendLoading.style.display = "none";
    recommendCountBadge.textContent = `${data.recommendations.length} Evaluated`;
    renderRecommendations(data.recommendations);
    highlightTopRecommendationOnMap(data.recommendations);

  } catch (err) {
    recommendLoading.style.display = "none";
    recommendError.style.display = "block";
    recommendError.innerHTML = `<p>⚠️ Unable to load recommendations: ${err.message}. Make sure Flask is running on port 5000.</p>`;
  }
}

function renderRecommendations(recommendations) {
  if (!recommendations || !recommendations.length) {
    recommendList.innerHTML = `<div class="error-state"><p>No stations matched the selected criteria.</p></div>`;
    return;
  }

  recommendList.innerHTML = recommendations.map(r => {
    const isTop = r.rank === 1 && r.is_available;
    const isCongested = !r.is_available;
    const cardClass = isTop ? "station-card top-pick" : (isCongested ? "station-card congested" : "station-card");

    const rankLabel = isTop ? "🌟 #1 Recommended" : `#${r.rank}`;
    const scoreColorClass = r.recommendation_score >= 80 ? "badge-success" : (r.recommendation_score >= 50 ? "badge-warning" : "badge-danger");

    return `
      <div class="${cardClass}">
        <div class="card-top">
          <div class="station-title-group">
            <span class="rank-badge">${rankLabel}</span>
            <span class="station-name">${escapeHtml(r.station_name)}</span>
            <span class="badge ${scoreColorClass}">Score: ${r.recommendation_score}/100</span>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem;">
            ${r.latitude && r.longitude ? `<button class="btn-card-map" type="button" onclick="focusStationOnMap(${r.station_id})">📍 View on Map</button>` : ""}
            ${r.is_available 
              ? `<span class="badge badge-success">● ${r.available_ports}/${r.total_ports} Ports Available</span>` 
              : `<span class="badge badge-danger">✕ Full (Wait Expected)</span>`}
          </div>
        </div>

        <div class="station-meta-grid">
          <div class="meta-item">
            <span class="label">Location</span>
            <span class="val">${escapeHtml(r.location)}</span>
          </div>
          <div class="meta-item">
            <span class="label">Sample Distance</span>
            <span class="val">${r.distance_km} km</span>
          </div>
          <div class="meta-item">
            <span class="label">Charger & Power</span>
            <span class="val">${escapeHtml(r.charger_type)} (${r.capacity_kw} kW)</span>
          </div>
          <div class="meta-item">
            <span class="label">Est. Queue Wait</span>
            <span class="val">${r.estimated_wait_minutes} mins</span>
          </div>
        </div>

        <div>
          <span style="font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase; font-weight: 600;">Recommendation Rationale:</span>
          <ul class="reasons-list">
            ${r.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("")}
          </ul>
        </div>
      </div>
    `;
  }).join("");
}

// ============================================================================
// 4. DEMAND PREDICTION API CALL (MODULE 4)
// ============================================================================
async function fetchDemandPrediction() {
  const hour = demandHourSelect.value;
  const day = demandDaySelect ? demandDaySelect.value : 2;
  const charger = chargerTypeSelect.value;

  try {
    const res = await fetch(`${API_BASE}/api/demand?hour=${hour}&day_of_week=${day}&charger_type=${encodeURIComponent(charger)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const data = json.data;

    demandKwh.textContent = `${data.predicted_demand_kwh} kWh`;
    demandLevelBadge.textContent = data.demand_level;

    if (data.demand_level.toLowerCase() === "low") {
      demandLevelBadge.className = "badge badge-success";
    } else if (data.demand_level.toLowerCase() === "medium") {
      demandLevelBadge.className = "badge badge-warning";
    } else {
      demandLevelBadge.className = "badge badge-danger";
    }

    modelName.textContent = data.model_used;
    demandAdvisory.textContent = data.advisory;

    // Update ML model evaluation metrics and training split dynamically from backend
    const meta = data.metadata || {
      metrics: data.metrics,
      dataset: data.dataset,
      is_available: data.is_ml_model
    };
    updateModelMetadataUI(meta);

    renderHourlyForecastChart(data.hourly_curve, parseInt(hour));

  } catch (err) {
    demandKwh.textContent = "Error";
    demandAdvisory.textContent = `Demand API currently unavailable: ${err.message}`;
    updateModelMetadataUI(null);
  }
}

function updateModelMetadataUI(meta) {
  if (!meta || !meta.is_available) {
    if (metricMae) metricMae.textContent = "Unavailable";
    if (metricRmse) metricRmse.textContent = "Unavailable";
    if (metricSplit) metricSplit.textContent = "Unavailable";
    if (metricTrainRecords) metricTrainRecords.textContent = "Unavailable";
    if (modelDatasetBadge) modelDatasetBadge.textContent = "Baseline Mode (Metadata Unavailable)";
    return;
  }

  // MAE and RMSE metrics
  if (meta.metrics && typeof meta.metrics === "object") {
    if (metricMae) {
      metricMae.textContent = meta.metrics.MAE != null 
        ? `${Number(meta.metrics.MAE).toFixed(2)} kWh` 
        : "Unavailable";
    }
    if (metricRmse) {
      metricRmse.textContent = meta.metrics.RMSE != null 
        ? `${Number(meta.metrics.RMSE).toFixed(2)} kWh` 
        : "Unavailable";
    }
  } else {
    if (metricMae) metricMae.textContent = "Unavailable";
    if (metricRmse) metricRmse.textContent = "Unavailable";
  }

  // Chronological Split description
  if (metricSplit) {
    metricSplit.textContent = meta.split_type || "Chronological Split";
  }

  // Trained records count formatted with locale thousands separator
  if (metricTrainRecords) {
    metricTrainRecords.textContent = meta.train_samples != null 
      ? Number(meta.train_samples).toLocaleString() 
      : "Unavailable";
  }

  // Dataset badge
  if (modelDatasetBadge) {
    modelDatasetBadge.textContent = meta.dataset || meta.model_type || "Random Forest Regressor";
  }
}

function renderHourlyForecastChart(curve, activeHour) {
  if (!curve || !curve.length) return;
  const maxKwh = Math.max(...curve.map(c => c.predicted_demand_kwh || c.predicted_kwh || 1.0));

  hourlyChart.innerHTML = curve.map(item => {
    const kwh = item.predicted_demand_kwh || item.predicted_kwh || 0;
    const heightPercent = Math.max(12, Math.round((kwh / maxKwh) * 95));
    const isCurrent = item.hour === activeHour;
    
    let colorClass = "bar-column";
    if (item.demand_level.toLowerCase() === "medium") colorClass += " high-demand";
    if (item.demand_level.toLowerCase() === "high") colorClass += " peak-demand";
    if (isCurrent) colorClass += " active-hour";

    const borderStyle = isCurrent ? "border: 2px solid #ffffff; box-shadow: 0 0 8px #10b981;" : "";

    return `
      <div class="bar-wrapper" title="${item.label}: ${kwh} kWh (${item.demand_level})">
        <div class="bar-tooltip">${item.label}: ${kwh} kWh (${item.demand_level})</div>
        <div class="${colorClass}" style="height: ${heightPercent}%; ${borderStyle}"></div>
        <span class="bar-time" style="${isCurrent ? 'color: #10b981; font-weight: bold;' : ''}">${item.hour}</span>
      </div>
    `;
  }).join("");
}

function escapeHtml(text) {
  if (!text) return "";
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

// ============================================================================
// STAGE 6: AUTHENTICATION & ROLE-BASED ACCESS CONTROL CONTROLLER
// ============================================================================
let currentCsrfToken = "";
let currentUser = null;

async function fetchCsrfToken() {
  try {
    const res = await fetch(`${API_BASE}/api/auth/csrf`, { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      currentCsrfToken = data.csrf_token || "";
    }
  } catch (err) {
    console.warn("[ChargeFindr AI] Failed to fetch CSRF token:", err.message);
  }
}

async function fetchCurrentUser() {
  try {
    const res = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      if (data.csrf_token) currentCsrfToken = data.csrf_token;
      if (data.authenticated && data.user) {
        currentUser = data.user;
      } else {
        currentUser = null;
      }
      renderAuthNav();
    }
  } catch (err) {
    console.warn("[ChargeFindr AI] Failed to check user session:", err.message);
  }
}

function renderAuthNav() {
  const container = document.getElementById("auth-nav-container");
  if (!container) return;

  if (currentUser) {
    const isAdmin = currentUser.role === "admin";
    const adminBtnHtml = isAdmin 
      ? `<button type="button" id="btn-open-admin" class="btn btn-sm btn-secondary" title="Open Admin Telemetry">🛡️ Admin</button>` 
      : "";

    container.innerHTML = `
      <div class="user-badge" title="${escapeHtml(currentUser.email)}">
        <span>👤 ${escapeHtml(currentUser.full_name)}</span>
        <span class="role-tag ${escapeHtml(currentUser.role)}">${escapeHtml(currentUser.role)}</span>
      </div>
      ${adminBtnHtml}
      <button type="button" id="btn-logout" class="btn btn-sm btn-secondary" title="Sign out of your account">🚪 Sign Out</button>
    `;

    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
      btnLogout.addEventListener("click", handleLogout);
    }

    const btnOpenAdmin = document.getElementById("btn-open-admin");
    if (btnOpenAdmin) {
      btnOpenAdmin.addEventListener("click", openAdminDashboard);
    }
  } else {
    container.innerHTML = `
      <button type="button" id="btn-open-login" class="btn btn-sm btn-secondary">🔑 Sign In</button>
      <button type="button" id="btn-open-register" class="btn btn-sm btn-primary">📝 Register</button>
    `;

    const btnOpenLogin = document.getElementById("btn-open-login");
    if (btnOpenLogin) {
      btnOpenLogin.addEventListener("click", () => openAuthModal("login"));
    }

    const btnOpenRegister = document.getElementById("btn-open-register");
    if (btnOpenRegister) {
      btnOpenRegister.addEventListener("click", () => openAuthModal("register"));
    }
  }
}

function openAuthModal(initialTab = "login") {
  const modal = document.getElementById("auth-modal-backdrop");
  const feedback = document.getElementById("auth-feedback");
  if (!modal) return;

  if (feedback) {
    feedback.style.display = "none";
    feedback.className = "auth-feedback";
    feedback.innerHTML = "";
  }

  switchAuthTab(initialTab);
  modal.style.display = "flex";
}

function closeAuthModal() {
  const modal = document.getElementById("auth-modal-backdrop");
  if (modal) modal.style.display = "none";
}

function switchAuthTab(tab) {
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  const formLogin = document.getElementById("form-login");
  const formRegister = document.getElementById("form-register");
  const feedback = document.getElementById("auth-feedback");

  if (feedback) feedback.style.display = "none";

  if (tab === "register") {
    if (tabLogin) tabLogin.classList.remove("active");
    if (tabRegister) tabRegister.classList.add("active");
    if (formLogin) formLogin.style.display = "none";
    if (formRegister) formRegister.style.display = "flex";
  } else {
    if (tabLogin) tabLogin.classList.add("active");
    if (tabRegister) tabRegister.classList.remove("active");
    if (formLogin) formLogin.style.display = "flex";
    if (formRegister) formRegister.style.display = "none";
  }
}

function showAuthFeedback(msg, type = "error") {
  const feedback = document.getElementById("auth-feedback");
  if (!feedback) return;
  feedback.className = `auth-feedback ${type}`;
  feedback.textContent = msg;
  feedback.style.display = "block";
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const emailInput = document.getElementById("login-email");
  const passInput = document.getElementById("login-password");
  const btnSubmit = document.getElementById("btn-submit-login");

  if (!emailInput || !passInput) return;

  btnSubmit.disabled = true;
  btnSubmit.textContent = "Signing in...";

  try {
    if (!currentCsrfToken) await fetchCsrfToken();

    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify({
        email: emailInput.value.trim(),
        password: passInput.value
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      currentUser = data.user;
      if (data.csrf_token) currentCsrfToken = data.csrf_token;
      renderAuthNav();
      closeAuthModal();
      passInput.value = "";
    } else {
      showAuthFeedback(data.error || "Login failed.", "error");
    }
  } catch (err) {
    showAuthFeedback(`Network error: ${err.message}`, "error");
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Sign In";
  }
}

async function handleRegisterSubmit(e) {
  e.preventDefault();
  const nameInput = document.getElementById("register-name");
  const emailInput = document.getElementById("register-email");
  const passInput = document.getElementById("register-password");
  const btnSubmit = document.getElementById("btn-submit-register");

  if (!nameInput || !emailInput || !passInput) return;

  btnSubmit.disabled = true;
  btnSubmit.textContent = "Creating account...";

  try {
    if (!currentCsrfToken) await fetchCsrfToken();

    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify({
        full_name: nameInput.value.trim(),
        email: emailInput.value.trim(),
        password: passInput.value
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showAuthFeedback("Account created! Please sign in with your credentials.", "success");
      const loginEmail = document.getElementById("login-email");
      if (loginEmail) loginEmail.value = emailInput.value.trim();
      passInput.value = "";
      setTimeout(() => switchAuthTab("login"), 1400);
    } else {
      showAuthFeedback(data.error || "Registration failed.", "error");
    }
  } catch (err) {
    showAuthFeedback(`Network error: ${err.message}`, "error");
  } finally {
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Create Account";
  }
}

async function handleLogout() {
  try {
    if (!currentCsrfToken) await fetchCsrfToken();

    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      }
    });
  } catch (err) {
    console.warn("[ChargeFindr AI] Logout notice:", err.message);
  } finally {
    currentUser = null;
    await fetchCsrfToken();
    renderAuthNav();
  }
}

async function openAdminDashboard() {
  const modal = document.getElementById("admin-modal-backdrop");
  const content = document.getElementById("admin-telemetry-content");
  if (!modal || !content) return;

  modal.style.display = "flex";
  content.innerHTML = `<div class="text-center" style="color: var(--text-muted); padding: 1rem;">Querying database telemetry...</div>`;

  try {
    const res = await fetch(`${API_BASE}/api/admin/overview`, { credentials: "include" });
    const data = await res.json();

    if (res.ok && data.success) {
      const d = data.data;
      content.innerHTML = `
        <div style="font-size:0.85rem; color: var(--text-muted); margin-bottom: 0.75rem;">
          Verified Administrator Session: <strong style="color: var(--accent-green);">${escapeHtml(currentUser ? currentUser.full_name : "Admin")}</strong>
        </div>
        <div class="admin-stats-grid">
          <div class="admin-stat-box">
            <div class="admin-stat-num">${d.total_users}</div>
            <div class="admin-stat-label">Registered Users</div>
          </div>
          <div class="admin-stat-box">
            <div class="admin-stat-num">${d.total_stations}</div>
            <div class="admin-stat-label">Charging Stations</div>
          </div>
        </div>
        <div style="margin-top: 1rem; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.75rem;">
          <div style="font-size:0.82rem; font-weight:600; color:var(--text-main); margin-bottom:0.4rem;">Security & Database Health</div>
          <p style="font-size:0.78rem; color:var(--text-muted);">Database: <strong style="color:#10b981;">Connected (MySQL)</strong></p>
          <p style="font-size:0.78rem; color:var(--text-muted); margin-top:0.2rem;">Protection: <strong style="color:var(--accent-blue);">${escapeHtml(d.security_mode)}</strong></p>
        </div>
      `;
    } else {
      content.innerHTML = `<div class="auth-feedback error">${escapeHtml(data.error || "Failed to load admin telemetry.")}</div>`;
    }
  } catch (err) {
    content.innerHTML = `<div class="auth-feedback error">Network error: ${escapeHtml(err.message)}</div>`;
  }
}

function initAuthSystem() {
  fetchCsrfToken();
  fetchCurrentUser();

  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  if (tabLogin) tabLogin.addEventListener("click", () => switchAuthTab("login"));
  if (tabRegister) tabRegister.addEventListener("click", () => switchAuthTab("register"));

  const btnCloseAuth = document.getElementById("btn-close-auth-modal");
  if (btnCloseAuth) btnCloseAuth.addEventListener("click", closeAuthModal);

  const authBackdrop = document.getElementById("auth-modal-backdrop");
  if (authBackdrop) {
    authBackdrop.addEventListener("click", (e) => {
      if (e.target === authBackdrop) closeAuthModal();
    });
  }

  const btnCloseAdmin = document.getElementById("btn-close-admin-modal");
  if (btnCloseAdmin) {
    btnCloseAdmin.addEventListener("click", () => {
      const modal = document.getElementById("admin-modal-backdrop");
      if (modal) modal.style.display = "none";
    });
  }

  const adminBackdrop = document.getElementById("admin-modal-backdrop");
  if (adminBackdrop) {
    adminBackdrop.addEventListener("click", (e) => {
      if (e.target === adminBackdrop) adminBackdrop.style.display = "none";
    });
  }

  const formLogin = document.getElementById("form-login");
  if (formLogin) formLogin.addEventListener("submit", handleLoginSubmit);

  const formRegister = document.getElementById("form-register");
  if (formRegister) formRegister.addEventListener("submit", handleRegisterSubmit);
}
