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
const GOOGLE_MAPS_API_KEY = "AIzaSyBOlxisAwTkxcKOft9a2b8kvaF8ZTu1-uk";

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
const metricR2 = document.getElementById("metric-r2");
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

let dashboardInitialized = false;

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  initAuthSystem();
});

function loadDashboardData() {
  if (dashboardInitialized) return;
  dashboardInitialized = true;
  populateHourDropdown();
  initMapLoader();
  checkBackendHealth();
  fetchStationLocations();
  fetchAllStations();
  fetchRecommendations();
  fetchDemandPrediction();
}

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

  // Delegated click and keyboard interaction for hourly demand chart bars
  if (hourlyChart) {
    hourlyChart.addEventListener("click", (e) => {
      const wrapper = e.target.closest(".bar-wrapper");
      if (!wrapper) return;
      const h = wrapper.getAttribute("data-hour");
      if (h != null) window.selectDemandHour(h);
    });
    hourlyChart.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        const wrapper = e.target.closest(".bar-wrapper");
        if (!wrapper) return;
        e.preventDefault();
        const h = wrapper.getAttribute("data-hour");
        if (h != null) window.selectDemandHour(h);
      }
    });
  }
}

// Select an hour on the demand chart and refresh predictions
window.selectDemandHour = function(h) {
  if (h == null || !demandHourSelect) return;
  const strHour = String(h);
  // Avoid duplicate API call if this hour is already selected
  if (demandHourSelect.value === strHour) return;
  demandHourSelect.value = strHour;
  fetchDemandPrediction();
};

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
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:var(--text-muted); text-align:center; padding:1.5rem;">
          <span style="font-size:2.5rem; margin-bottom:0.5rem;">🗺️</span>
          <strong style="color:var(--text-main); font-size:1.05rem;">Google Maps Standby Mode</strong>
          <p style="font-size:0.85rem; max-width:480px; margin-top:0.4rem; color:var(--text-muted);">
            To render the interactive satellite/street map and road routing, add your restricted Google Maps API key in <code>frontend/script.js</code>.
          </p>
          <span style="margin-top:0.75rem; font-size:0.78rem; color:#047857; background:#ecfdf5; border:1px solid #a7f3d0; padding:0.3rem 0.75rem; border-radius:9999px; font-weight:600;">
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

  const lightMapStyle = [
    { elementType: "geometry", stylers: [{ color: "#f8fafc" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#ffffff" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#334155" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
    { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#e2e8f0" }] },
    { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#475569" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#e0f2fe" }] },
    { featureType: "water", elementType: "labels.text.fill", stylers: [{ color: "#0284c7" }] },
    { featureType: "poi", elementType: "geometry", stylers: [{ color: "#f1f5f9" }] },
    { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#ecfdf5" }] },
    { featureType: "poi", elementType: "labels.text.fill", stylers: [{ color: "#64748b" }] }
  ];

  googleMap = new google.maps.Map(mapContainer, {
    center: hyderabadCenter,
    zoom: 12,
    styles: lightMapStyle,
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
        <div style="font-size:0.7rem; color:var(--text-muted); margin-top:3px;">
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
      statusText.textContent = "Online";
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
    populateBookingStationsDropdown();
    populateWalkinStationsDropdown();

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

function renderAlertItem(alert) {
  const congested = alert.congested_station || {};
  const alt = alert.recommended_alternative;

  // Working "View on Map" action only if existing map functions support it
  let mapBtn = "";
  if (alt && alt.station_id != null && typeof window.focusStationOnMap === "function") {
    mapBtn = ` <button type="button" class="btn-card-map" style="display:inline-flex; align-items:center; padding: 0.2rem 0.55rem; font-size: 0.75rem; margin-left: 0.4rem; cursor: pointer;" onclick="window.focusStationOnMap(${Number(alt.station_id)})">🗺️ View on Map</button>`;
  }

  // Use backend's formatted message if provided
  if (alert.message) {
    return `${escapeHtml(alert.message)}${mapBtn}`;
  }

  // Safe fallback if message is absent:
  const availText = congested.available_ports != null ? `${congested.available_ports} ports available` : "unknown ports";
  const waitText = congested.estimated_wait_minutes != null ? `${congested.estimated_wait_minutes} min wait` : "unverified wait";
  const cName = escapeHtml(congested.station_name || "Station");
  const cLoc = escapeHtml(congested.location || "Location");

  if (alt) {
    const altName = escapeHtml(alt.station_name || "Alternative Station");
    const altWait = alt.estimated_wait_minutes != null ? `~${alt.estimated_wait_minutes} min wait` : "minimal queue";
    return `Notice: ${cName} (${cLoc}) is currently congested (${availText}, ${waitText}). Recommend re-routing to ${altName} (${altWait}).${mapBtn}`;
  } else {
    return `Notice: ${cName} (${cLoc}) is currently congested (${availText}, ${waitText}). No low-wait alternatives currently available.`;
  }
}

async function fetchCongestionAlerts() {
  if (isFetchingAlerts) return;
  isFetchingAlerts = true;

  try {
    const res = await fetch(`${API_BASE}/api/stations/alerts`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.success && data.has_alert && Array.isArray(data.alerts) && data.alerts.length > 0) {
      if (alertBanner && alertMessage) {
        alertBanner.style.display = "flex";
        alertBanner.style.alignItems = "flex-start";

        if (data.alerts.length === 1) {
          alertMessage.innerHTML = `<strong>Smart Alert:</strong> ${renderAlertItem(data.alerts[0])}`;
        } else {
          const count = data.alerts.length;
          const itemsHtml = data.alerts
            .map(a => `<li style="margin-top: 0.25rem;">${renderAlertItem(a)}</li>`)
            .join("");
          alertMessage.innerHTML = `<div><strong>Smart Alerts (${count} stations congested):</strong><ul style="margin: 0.25rem 0 0 1.2rem; padding: 0;">${itemsHtml}</ul></div>`;
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
  const btnRecommend = document.getElementById("btn-recommend");
  if (btnRecommend) btnRecommend.disabled = true;

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

    recommendCountBadge.textContent = `${data.recommendations.length} Evaluated`;
    renderRecommendations(data.recommendations);
    highlightTopRecommendationOnMap(data.recommendations);

  } catch (err) {
    recommendError.style.display = "block";
    recommendError.innerHTML = `<p>⚠️ Unable to load recommendations: ${err.message}. Make sure Flask is running on port 5000.</p>`;
    recommendCountBadge.textContent = "Unavailable";
  } finally {
    recommendLoading.style.display = "none";
    if (btnRecommend) btnRecommend.disabled = false;
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
    if (metricR2) metricR2.textContent = "Unavailable";
    if (metricSplit) metricSplit.textContent = "Unavailable";
    if (metricTrainRecords) metricTrainRecords.textContent = "Unavailable";
    if (modelDatasetBadge) modelDatasetBadge.textContent = "Baseline Mode (Metadata Unavailable)";
    return;
  }

  // MAE, RMSE, and R² evaluation metrics
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
    if (metricR2) {
      const r2 = meta.metrics.R2_Score != null ? meta.metrics.R2_Score : meta.metrics.R2;
      metricR2.textContent = (r2 != null && !isNaN(Number(r2)))
        ? Number(r2).toFixed(4)
        : "Unavailable";
    }
  } else {
    if (metricMae) metricMae.textContent = "Unavailable";
    if (metricRmse) metricRmse.textContent = "Unavailable";
    if (metricR2) metricR2.textContent = "Unavailable";
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

  // Model type badge
  if (modelDatasetBadge) {
    modelDatasetBadge.textContent = meta.model_type || "Random Forest Regressor";
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
      <div class="bar-wrapper" data-hour="${item.hour}" tabindex="0" role="button" aria-label="${item.label}: ${kwh} kWh (${item.demand_level})" title="${item.label}: ${kwh} kWh (${item.demand_level})">
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
        showDashboardView();
        loadDashboardData();
      } else {
        currentUser = null;
        showLandingView();
      }
      renderAuthNav();
    } else {
      showLandingView();
    }
  } catch (err) {
    console.warn("[ChargeFindr AI] Failed to check user session:", err.message);
    showLandingView();
  }
}

function showLandingView() {
  const landing = document.getElementById("auth-landing-view");
  const app = document.getElementById("app-view");
  if (landing) landing.style.display = "flex";
  if (app) app.style.display = "none";
}

function showDashboardView() {
  const landing = document.getElementById("auth-landing-view");
  const app = document.getElementById("app-view");
  if (landing) landing.style.display = "none";
  if (app) app.style.display = "block";
  renderAuthNav();
}

function renderAuthNav() {
  const container = document.getElementById("auth-nav-container");
  if (!container) return;

  const userBadge = document.getElementById("user-badge");
  const btnAdminNav = document.getElementById("btn-admin-modal-nav");
  const btnLogout = document.getElementById("btn-logout");

  if (currentUser) {
    if (userBadge) {
      userBadge.style.display = "inline-flex";
      userBadge.innerHTML = `<span>👤 ${escapeHtml(currentUser.full_name)}</span> <span class="role-tag ${escapeHtml(currentUser.role)}">${escapeHtml(currentUser.role)}</span>`;
    }
    if (btnAdminNav) {
      btnAdminNav.style.display = currentUser.role === "admin" ? "inline-flex" : "none";
    }
    if (btnLogout) {
      btnLogout.style.display = "inline-flex";
    }
  } else {
    if (userBadge) userBadge.style.display = "none";
    if (btnAdminNav) btnAdminNav.style.display = "none";
    if (btnLogout) btnLogout.style.display = "none";
  }
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
      showDashboardView();
      loadDashboardData();
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
  const confirmPassInput = document.getElementById("register-confirm-password");
  const btnSubmit = document.getElementById("btn-submit-register");

  if (!nameInput || !emailInput || !passInput || !confirmPassInput) return;

  if (passInput.value !== confirmPassInput.value) {
    showAuthFeedback("Passwords do not match.", "error");
    return;
  }

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
        password: passInput.value,
        confirm_password: confirmPassInput.value
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showAuthFeedback("Account created! Please sign in with your credentials.", "success");
      const loginEmail = document.getElementById("login-email");
      if (loginEmail) loginEmail.value = emailInput.value.trim();
      passInput.value = "";
      confirmPassInput.value = "";
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
    dashboardInitialized = false;
    await fetchCsrfToken();
    showLandingView();
    switchAuthTab("login");
  }
}

// ============================================================================
// ADMIN DASHBOARD & STATION MANAGEMENT CRUD
// ============================================================================
let adminStationsList = [];

function switchAdminTab(tab) {
  const tabOverview = document.getElementById("tab-admin-overview");
  const tabStations = document.getElementById("tab-admin-stations");
  const secOverview = document.getElementById("admin-section-overview");
  const secStations = document.getElementById("admin-section-stations");

  if (tab === "stations") {
    if (tabOverview) tabOverview.classList.remove("active");
    if (tabStations) tabStations.classList.add("active");
    if (secOverview) secOverview.style.display = "none";
    if (secStations) secStations.style.display = "block";
    loadAdminStations();
  } else {
    if (tabOverview) tabOverview.classList.add("active");
    if (tabStations) tabStations.classList.remove("active");
    if (secOverview) secOverview.style.display = "block";
    if (secStations) secStations.style.display = "none";
  }
}

async function openAdminDashboard() {
  const modal = document.getElementById("admin-modal-backdrop");
  const content = document.getElementById("admin-telemetry-content");
  if (!modal || !content) return;

  modal.style.display = "flex";
  switchAdminTab("overview");
  content.innerHTML = `<div class="text-center" style="color: var(--text-muted); padding: 1rem;">Querying database telemetry...</div>`;

  try {
    const res = await fetch(`${API_BASE}/api/admin/overview`, { credentials: "include" });
    const data = await res.json();

    if (res.ok && data.success) {
      const d = data.data;

      let adminCount = 0;
      let userCount = 0;
      if (Array.isArray(d.role_breakdown)) {
        d.role_breakdown.forEach(item => {
          const role = String(item.role || "").toLowerCase();
          const count = Number(item.count) || 0;
          if (role === "admin") adminCount += count;
          else if (role === "user") userCount += count;
        });
      }

      content.innerHTML = `
        <div style="font-size:0.85rem; color: var(--text-muted); margin-bottom: 0.75rem;">
          Verified Administrator Session: <strong style="color: var(--accent-green);">${escapeHtml(currentUser ? currentUser.full_name : "Admin")}</strong>
        </div>
        <div class="admin-stats-grid">
          <div class="admin-stat-box">
            <div class="admin-stat-num">${d.total_users != null ? d.total_users : "--"}</div>
            <div class="admin-stat-label">Registered Users</div>
          </div>
          <div class="admin-stat-box">
            <div class="admin-stat-num">${d.total_stations != null ? d.total_stations : "--"}</div>
            <div class="admin-stat-label">Charging Stations</div>
          </div>
        </div>
        <div style="margin-top: 0.75rem; background: var(--bg-input); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; font-size: 0.8rem;">
          <div style="font-weight:600; color:var(--text-main); margin-bottom:0.35rem;">Account Role Breakdown:</div>
          <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            <span>🛡️ Administrators: <strong style="color: var(--accent-blue);">${adminCount}</strong></span>
            <span>👤 Regular Users: <strong style="color: var(--text-main);">${userCount}</strong></span>
          </div>
        </div>
        <div style="margin-top: 0.75rem; background: var(--bg-subtle); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.75rem;">
          <div style="font-size:0.82rem; font-weight:600; color:var(--text-main); margin-bottom:0.4rem;">Security & Database Health</div>
          <p style="font-size:0.78rem; color:var(--text-muted);">Database: <strong style="color:#10b981;">Connected (MySQL)</strong></p>
          <p style="font-size:0.78rem; color:var(--text-muted); margin-top:0.2rem;">Protection: <strong style="color:var(--accent-blue);">${escapeHtml(d.security_mode || "Strict")}</strong></p>
        </div>
      `;
    } else {
      content.innerHTML = `<div class="auth-feedback error">${escapeHtml(data.error || "Failed to load admin telemetry.")}</div>`;
    }
  } catch (err) {
    content.innerHTML = `<div class="auth-feedback error">Network error: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadAdminStations() {
  const tbody = document.getElementById("admin-stations-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" class="text-center">Loading stations from database...</td></tr>`;

  try {
    const res = await fetch(`${API_BASE}/api/stations`, { credentials: "include" });
    const data = await res.json();
    if (res.ok && data.success) {
      adminStationsList = data.data || [];
      renderAdminStationsTable();
    } else {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:var(--accent-red);">${escapeHtml(data.error || "Failed to load stations.")}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:var(--accent-red);">Network error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderAdminStationsTable() {
  const tbody = document.getElementById("admin-stations-tbody");
  if (!tbody) return;

  if (adminStationsList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">No charging stations found.</td></tr>`;
    return;
  }

  tbody.innerHTML = adminStationsList.map(stn => `
    <tr>
      <td>#${stn.station_id}</td>
      <td><strong>${escapeHtml(stn.station_name)}</strong></td>
      <td>${escapeHtml(stn.location)}</td>
      <td><span class="badge badge-secondary">${escapeHtml(stn.charger_type)}</span></td>
      <td>${stn.available_ports != null ? stn.available_ports : "--"} / ${stn.total_ports != null ? stn.total_ports : "--"}</td>
      <td>${stn.estimated_wait_minutes != null ? stn.estimated_wait_minutes + "m" : "--"}</td>
      <td>
        <button type="button" class="btn-action-edit" onclick="handleEditStationClick(${stn.station_id})">✏️ Edit</button>
        <button type="button" class="btn-action-delete" onclick="handleDeleteStationClick(${stn.station_id})">🗑️ Delete</button>
      </td>
    </tr>
  `).join("");
}

window.handleEditStationClick = function(id) {
  const stn = adminStationsList.find(s => s.station_id === id);
  if (!stn) return;

  const form = document.getElementById("admin-station-form");
  if (!form) return;

  document.getElementById("admin-station-id").value = stn.station_id;
  document.getElementById("admin-station-name").value = stn.station_name;
  document.getElementById("admin-station-location").value = stn.location;
  document.getElementById("admin-station-charger").value = stn.charger_type || "Fast DC";
  document.getElementById("admin-station-capacity").value = stn.capacity_kw || 60;
  document.getElementById("admin-station-distance").value = stn.distance_km || 2.0;
  document.getElementById("admin-station-total-ports").value = stn.total_ports || 4;
  document.getElementById("admin-station-avail-ports").value = stn.available_ports != null ? stn.available_ports : 2;
  document.getElementById("admin-station-wait").value = stn.estimated_wait_minutes != null ? stn.estimated_wait_minutes : 5;
  document.getElementById("admin-station-demand").value = stn.demand_level || "Medium";
  document.getElementById("admin-station-lat").value = stn.latitude || "";
  document.getElementById("admin-station-lng").value = stn.longitude || "";

  document.getElementById("btn-save-station").textContent = "Update Station";
  form.style.display = "flex";
  form.scrollIntoView({ behavior: "smooth" });
};

window.handleDeleteStationClick = async function(id) {
  const stn = adminStationsList.find(s => s.station_id === id);
  const name = stn ? stn.station_name : `#${id}`;
  if (!confirm(`Are you sure you want to delete station "${name}"? This action cannot be undone.`)) {
    return;
  }

  try {
    if (!currentCsrfToken) await fetchCsrfToken();
    const res = await fetch(`${API_BASE}/api/admin/stations/${id}`, {
      method: "DELETE",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      }
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showAdminFeedback(`Station #${id} was deleted successfully.`, "success");
      loadAdminStations();
      fetchAllStations();
    } else {
      showAdminFeedback(data.error || "Failed to delete station.", "error");
    }
  } catch (err) {
    showAdminFeedback(`Network error: ${err.message}`, "error");
  }
};

async function handleAdminStationFormSubmit(e) {
  e.preventDefault();
  const idInput = document.getElementById("admin-station-id");
  const stationId = idInput ? idInput.value : "";
  const isEditing = Boolean(stationId);

  const payload = {
    station_name: document.getElementById("admin-station-name").value.trim(),
    location: document.getElementById("admin-station-location").value.trim(),
    charger_type: document.getElementById("admin-station-charger").value,
    capacity_kw: parseFloat(document.getElementById("admin-station-capacity").value),
    distance_km: parseFloat(document.getElementById("admin-station-distance").value),
    total_ports: parseInt(document.getElementById("admin-station-total-ports").value, 10),
    available_ports: parseInt(document.getElementById("admin-station-avail-ports").value, 10),
    estimated_wait_minutes: parseInt(document.getElementById("admin-station-wait").value, 10),
    demand_level: document.getElementById("admin-station-demand").value,
    latitude: document.getElementById("admin-station-lat").value ? parseFloat(document.getElementById("admin-station-lat").value) : null,
    longitude: document.getElementById("admin-station-lng").value ? parseFloat(document.getElementById("admin-station-lng").value) : null
  };

  const btnSave = document.getElementById("btn-save-station");
  btnSave.disabled = true;
  btnSave.textContent = isEditing ? "Updating..." : "Saving...";

  try {
    if (!currentCsrfToken) await fetchCsrfToken();
    const url = isEditing ? `${API_BASE}/api/admin/stations/${stationId}` : `${API_BASE}/api/admin/stations`;
    const method = isEditing ? "PUT" : "POST";

    const res = await fetch(url, {
      method: method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showAdminFeedback(data.message || "Station saved successfully.", "success");
      document.getElementById("admin-station-form").reset();
      document.getElementById("admin-station-id").value = "";
      document.getElementById("admin-station-form").style.display = "none";
      loadAdminStations();
      fetchAllStations();
    } else {
      showAdminFeedback(data.error || "Failed to save station.", "error");
    }
  } catch (err) {
    showAdminFeedback(`Network error: ${err.message}`, "error");
  } finally {
    btnSave.disabled = false;
    btnSave.textContent = isEditing ? "Update Station" : "Save Station";
  }
}

function showAdminFeedback(msg, type = "error") {
  const fb = document.getElementById("admin-feedback");
  if (!fb) return;
  fb.className = `auth-feedback ${type}`;
  fb.textContent = msg;
  fb.style.display = "block";
}

function initAuthSystem() {
  fetchCsrfToken();
  fetchCurrentUser();

  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  if (tabLogin) tabLogin.addEventListener("click", () => switchAuthTab("login"));
  if (tabRegister) tabRegister.addEventListener("click", () => switchAuthTab("register"));

  const btnLogout = document.getElementById("btn-logout");
  if (btnLogout) btnLogout.addEventListener("click", handleLogout);

  const btnAdminNav = document.getElementById("btn-admin-modal-nav");
  if (btnAdminNav) btnAdminNav.addEventListener("click", openAdminDashboard);

  const tabAdminOverview = document.getElementById("tab-admin-overview");
  if (tabAdminOverview) tabAdminOverview.addEventListener("click", () => switchAdminTab("overview"));

  const tabAdminStations = document.getElementById("tab-admin-stations");
  if (tabAdminStations) tabAdminStations.addEventListener("click", () => switchAdminTab("stations"));

  const btnToggleAdd = document.getElementById("btn-toggle-add-station");
  if (btnToggleAdd) {
    btnToggleAdd.addEventListener("click", () => {
      const form = document.getElementById("admin-station-form");
      if (form) {
        if (form.style.display === "none") {
          form.reset();
          document.getElementById("admin-station-id").value = "";
          document.getElementById("btn-save-station").textContent = "Save Station";
          form.style.display = "flex";
        } else {
          form.style.display = "none";
        }
      }
    });
  }

  const btnCancelStation = document.getElementById("btn-cancel-station");
  if (btnCancelStation) {
    btnCancelStation.addEventListener("click", () => {
      const form = document.getElementById("admin-station-form");
      if (form) form.style.display = "none";
    });
  }

  const stationForm = document.getElementById("admin-station-form");
  if (stationForm) stationForm.addEventListener("submit", handleAdminStationFormSubmit);

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

  // Initialize Reserved Slot Booking & Rapid Queue systems
  initBookingAndQueueSystem();
}

// ============================================================================
// APPLICATION TAB SWITCHING & SUB-NAVIGATION
// ============================================================================
let activeAppTab = "dashboard";
let selectedBookingSlot = null;
let activeQueueTicketId = null;
let currentMissedBookingOriginal = null;

window.switchAppTab = function(tabName) {
  activeAppTab = tabName;

  // Update subnav buttons active state
  const tabs = ["dashboard", "book", "walkin", "my-bookings", "my-queue"];
  tabs.forEach(t => {
    const btn = document.getElementById(`nav-btn-${t}`);
    const view = document.getElementById(`view-${t}`);
    if (btn) {
      if (t === tabName) btn.classList.add("active");
      else btn.classList.remove("active");
    }
    if (view) {
      if (t === tabName) view.style.display = "block";
      else view.style.display = "none";
    }
  });

  // Trigger data loader for the active tab
  if (tabName === "book") {
    setupBookingTab();
  } else if (tabName === "walkin") {
    setupWalkinTab();
  } else if (tabName === "my-bookings") {
    loadMyBookings();
  } else if (tabName === "my-queue") {
    loadMyQueueTicket();
  } else if (tabName === "dashboard") {
    if (googleMap) {
      // Refresh map layout if needed
      google.maps.event.trigger(googleMap, "resize");
    }
  }
};

function initBookingAndQueueSystem() {
  // Booking Form Listeners
  const bookStationSelect = document.getElementById("book-station-select");
  if (bookStationSelect) bookStationSelect.addEventListener("change", handleBookingStationChange);

  const bookDateInput = document.getElementById("book-date");
  if (bookDateInput) {
    const todayStr = new Date().toISOString().split("T")[0];
    bookDateInput.min = todayStr;
    if (!bookDateInput.value) bookDateInput.value = todayStr;
    bookDateInput.addEventListener("change", loadAvailableSlots);
  }

  const bookDurationSelect = document.getElementById("book-duration");
  if (bookDurationSelect) bookDurationSelect.addEventListener("change", loadAvailableSlots);

  const btnConfirmBooking = document.getElementById("btn-confirm-booking");
  if (btnConfirmBooking) btnConfirmBooking.addEventListener("click", handleConfirmBookingSubmit);

  // Rapid Walk-in Form Listeners
  const walkinStationSelect = document.getElementById("walkin-station-select");
  if (walkinStationSelect) walkinStationSelect.addEventListener("change", handleWalkinStationChange);

  const formJoinQueue = document.getElementById("form-join-queue");
  if (formJoinQueue) formJoinQueue.addEventListener("submit", handleJoinQueueSubmit);

  const btnRefreshQueue = document.getElementById("btn-refresh-queue");
  if (btnRefreshQueue) btnRefreshQueue.addEventListener("click", loadMyQueueTicket);

  const btnLeaveQueue = document.getElementById("btn-leave-queue");
  if (btnLeaveQueue) btnLeaveQueue.addEventListener("click", handleLeaveQueueSubmit);

  // Close Alternative Modal
  const btnCloseAlt = document.getElementById("btn-close-alt-modal");
  if (btnCloseAlt) {
    btnCloseAlt.addEventListener("click", () => {
      const modal = document.getElementById("alternative-modal-backdrop");
      if (modal) modal.style.display = "none";
    });
  }

  const altBackdrop = document.getElementById("alternative-modal-backdrop");
  if (altBackdrop) {
    altBackdrop.addEventListener("click", (e) => {
      if (e.target === altBackdrop) altBackdrop.style.display = "none";
    });
  }

  // Admin tabs extension
  const tabAdminBookings = document.getElementById("tab-admin-bookings");
  if (tabAdminBookings) tabAdminBookings.addEventListener("click", () => switchAdminTab("bookings"));

  const tabAdminQueues = document.getElementById("tab-admin-queues");
  if (tabAdminQueues) tabAdminQueues.addEventListener("click", () => switchAdminTab("queues"));
}

// ============================================================================
// RESERVED SLOT BOOKING CONTROLLER
// ============================================================================
function setupBookingTab() {
  // Prefill driver name from current user
  const driverInput = document.getElementById("book-driver-name");
  if (driverInput && currentUser && currentUser.full_name && !driverInput.value) {
    driverInput.value = currentUser.full_name;
  }

  const dateInput = document.getElementById("book-date");
  if (dateInput && !dateInput.value) {
    dateInput.value = new Date().toISOString().split("T")[0];
  }

  populateBookingStationsDropdown();
}

function populateBookingStationsDropdown() {
  const select = document.getElementById("book-station-select");
  if (!select) return;

  const currentVal = select.value;
  select.innerHTML = `<option value="">-- Choose an EV Station --</option>`;

  allStationsData.forEach(stn => {
    const opt = document.createElement("option");
    opt.value = stn.station_id;
    opt.textContent = `${stn.station_name} (${stn.location}) — ${stn.charger_type}`;
    select.appendChild(opt);
  });

  if (currentVal && allStationsData.some(s => s.station_id == currentVal)) {
    select.value = currentVal;
    handleBookingStationChange();
  }
}

function handleBookingStationChange() {
  const select = document.getElementById("book-station-select");
  const pill = document.getElementById("book-station-info-pill");
  if (!select) return;

  const stationId = select.value;
  if (!stationId) {
    if (pill) pill.style.display = "none";
    renderEmptySlotsMatrix("Please choose an EV station on the left to see live slot availability.");
    return;
  }

  const stn = allStationsData.find(s => s.station_id == stationId);
  if (stn && pill) {
    document.getElementById("book-station-address").textContent = `📍 ${stn.location}`;
    document.getElementById("book-station-type").textContent = `⚡ ${stn.charger_type} (${stn.capacity_kw || 60} kW)`;
    document.getElementById("book-station-ports").textContent = `🔌 Total Ports: ${stn.total_ports || 4}`;
    pill.style.display = "flex";
  }

  loadAvailableSlots();
}

async function loadAvailableSlots() {
  const stationId = document.getElementById("book-station-select")?.value;
  const dateStr = document.getElementById("book-date")?.value;
  const duration = document.getElementById("book-duration")?.value || 60;
  const loading = document.getElementById("slots-loading");
  const matrix = document.getElementById("slots-matrix");
  const dateLabel = document.getElementById("slots-date-label");
  const confirmBox = document.getElementById("slot-confirmation-box");

  if (confirmBox) confirmBox.style.display = "none";
  selectedBookingSlot = null;

  if (!stationId || !dateStr) {
    renderEmptySlotsMatrix("Select an EV station and date on the left to check available slots.");
    return;
  }

  if (dateLabel) dateLabel.textContent = `Showing slots for ${dateStr} (${duration} mins)`;
  if (loading) loading.style.display = "flex";
  if (matrix) matrix.innerHTML = "";

  try {
    const res = await fetch(`${API_BASE}/api/bookings/available-slots?station_id=${stationId}&date=${dateStr}&duration=${duration}`, {
      credentials: "include"
    });
    const data = await res.json();

    if (loading) loading.style.display = "none";

    if (res.ok && data.success) {
      renderSlotsMatrix(data.slots || []);
    } else {
      renderEmptySlotsMatrix(data.error || "Failed to load slots for this date.");
    }
  } catch (err) {
    if (loading) loading.style.display = "none";
    renderEmptySlotsMatrix(`Network error loading slots: ${err.message}`);
  }
}

function renderEmptySlotsMatrix(message) {
  const matrix = document.getElementById("slots-matrix");
  if (!matrix) return;
  matrix.innerHTML = `<div class="slots-empty-notice">${escapeHtml(message)}</div>`;
}

function renderSlotsMatrix(slots) {
  const matrix = document.getElementById("slots-matrix");
  if (!matrix) return;

  if (!slots || slots.length === 0) {
    matrix.innerHTML = `<div class="slots-empty-notice">No slots available for the selected station and time window.</div>`;
    return;
  }

  matrix.innerHTML = "";
  slots.forEach(slot => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "slot-btn";

    let statusLabel = "";
    if (slot.is_past) {
      btn.classList.add("past");
      btn.disabled = true;
      statusLabel = "Past Time";
    } else if (!slot.available) {
      btn.classList.add("booked");
      btn.disabled = true;
      statusLabel = "Fully Booked";
    } else {
      btn.classList.add("available");
      statusLabel = `${slot.free_ports} free bay${slot.free_ports > 1 ? "s" : ""}`;
      btn.addEventListener("click", () => handleSelectSlot(slot, btn));
    }

    btn.innerHTML = `
      <span class="slot-time">${slot.start_time} - ${slot.end_time}</span>
      <span class="slot-status-text">${statusLabel}</span>
    `;
    matrix.appendChild(btn);
  });
}

function handleSelectSlot(slot, btnElement) {
  selectedBookingSlot = slot;

  // Clear previous selected styling
  const allBtns = document.querySelectorAll("#slots-matrix .slot-btn");
  allBtns.forEach(b => b.classList.remove("selected"));

  btnElement.classList.add("selected");

  // Show confirmation summary box
  const confirmBox = document.getElementById("slot-confirmation-box");
  const stationSelect = document.getElementById("book-station-select");
  const stationName = stationSelect.options[stationSelect.selectedIndex]?.text || "Selected Station";

  document.getElementById("confirm-slot-time").textContent = `${slot.start_time} to ${slot.end_time}`;
  document.getElementById("confirm-slot-station").textContent = stationName;
  document.getElementById("confirm-slot-duration").textContent = `${document.getElementById("book-duration").value} mins`;

  if (confirmBox) {
    confirmBox.style.display = "flex";
    confirmBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

async function handleConfirmBookingSubmit() {
  if (!selectedBookingSlot) {
    alert("Please select an available time slot first.");
    return;
  }

  const stationId = document.getElementById("book-station-select")?.value;
  const driverName = document.getElementById("book-driver-name")?.value.trim();
  const vehicleModel = document.getElementById("book-vehicle-model")?.value.trim();
  const vehicleReg = document.getElementById("book-vehicle-reg")?.value.trim();
  const bookingDate = document.getElementById("book-date")?.value;
  const duration = parseInt(document.getElementById("book-duration")?.value, 10);
  const feedback = document.getElementById("book-form-feedback");
  const btn = document.getElementById("btn-confirm-booking");

  if (!driverName || !vehicleModel || !vehicleReg) {
    showBookFeedback("Please fill out your driver full name, vehicle model, and registration number.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Reserving Slot...";

  try {
    if (!currentCsrfToken) await fetchCsrfToken();

    const payload = {
      station_id: parseInt(stationId, 10),
      driver_name: driverName,
      vehicle_model: vehicleModel,
      vehicle_reg_number: vehicleReg,
      booking_date: bookingDate,
      start_time: selectedBookingSlot.start_time,
      duration_minutes: duration
    };

    const res = await fetch(`${API_BASE}/api/bookings`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok && data.success) {
      showBookFeedback(`🎉 Success! Slot confirmed. Reference: ${data.booking.booking_reference} (Port #${data.booking.port_number}).`, "success");
      selectedBookingSlot = null;
      document.getElementById("slot-confirmation-box").style.display = "none";
      loadAvailableSlots();
      setTimeout(() => {
        if (confirm("Your slot reservation is confirmed! Would you like to view it in My Bookings?")) {
          switchAppTab("my-bookings");
        }
      }, 500);
    } else {
      showBookFeedback(data.error || "Failed to complete slot reservation.", "error");
      if (res.status === 409) {
        // Refresh slot list on race-condition conflict
        loadAvailableSlots();
      }
    }
  } catch (err) {
    showBookFeedback(`Network error during booking: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "⚡ Confirm & Book Slot Now";
  }
}

function showBookFeedback(msg, type = "error") {
  const fb = document.getElementById("book-form-feedback");
  if (!fb) return;
  fb.className = `auth-feedback ${type}`;
  fb.textContent = msg;
  fb.style.display = "block";
}

// ============================================================================
// RAPID WALK-IN CHARGING QUEUE CONTROLLER
// ============================================================================
function setupWalkinTab() {
  const driverInput = document.getElementById("walkin-driver-name");
  if (driverInput && currentUser && currentUser.full_name && !driverInput.value) {
    driverInput.value = currentUser.full_name;
  }

  populateWalkinStationsDropdown();
  checkUserActiveQueueAlert();
}

function populateWalkinStationsDropdown() {
  const select = document.getElementById("walkin-station-select");
  if (!select) return;

  const currentVal = select.value;
  select.innerHTML = `<option value="">-- Select an EV Station --</option>`;

  allStationsData.forEach(stn => {
    const opt = document.createElement("option");
    opt.value = stn.station_id;
    opt.textContent = `${stn.station_name} (${stn.location}) — ${stn.charger_type}`;
    select.appendChild(opt);
  });

  if (currentVal && allStationsData.some(s => s.station_id == currentVal)) {
    select.value = currentVal;
    handleWalkinStationChange();
  }
}

async function handleWalkinStationChange() {
  const select = document.getElementById("walkin-station-select");
  const metricsCard = document.getElementById("walkin-metrics-card");
  if (!select) return;

  const stationId = select.value;
  if (!stationId) {
    if (metricsCard) metricsCard.style.display = "none";
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/queue/status/${stationId}`, { credentials: "include" });
    const data = await res.json();

    if (res.ok && data.success) {
      document.getElementById("walkin-card-station-name").textContent = data.station_name;
      document.getElementById("walkin-card-location").textContent = data.location;
      document.getElementById("walkin-stat-ports").textContent = data.walkin_ports;
      document.getElementById("walkin-stat-waiting").textContent = data.waiting_count;
      document.getElementById("walkin-stat-wait").textContent = `${data.estimated_wait_minutes} m`;
      if (metricsCard) metricsCard.style.display = "block";
    }
  } catch (err) {
    console.warn("Could not load walk-in queue metrics:", err);
  }
}

async function checkUserActiveQueueAlert() {
  const alertBox = document.getElementById("walkin-has-active-alert");
  if (!alertBox) return;

  try {
    const res = await fetch(`${API_BASE}/api/queue/my`, { credentials: "include" });
    const data = await res.json();
    if (res.ok && data.success && data.ticket) {
      document.getElementById("walkin-active-alert-msg").textContent = `You already hold active ticket ${data.ticket.queue_ticket} at ${data.ticket.station_name} (Pos #${data.ticket.position}).`;
      alertBox.style.display = "flex";
    } else {
      alertBox.style.display = "none";
    }
  } catch (err) {
    alertBox.style.display = "none";
  }
}

async function handleJoinQueueSubmit(e) {
  e.preventDefault();
  const stationId = document.getElementById("walkin-station-select")?.value;
  const driverName = document.getElementById("walkin-driver-name")?.value.trim();
  const vehicleModel = document.getElementById("walkin-vehicle-model")?.value.trim();
  const vehicleReg = document.getElementById("walkin-vehicle-reg")?.value.trim();
  const chargerType = document.getElementById("walkin-charger-type")?.value;
  const feedback = document.getElementById("walkin-feedback");
  const btn = document.getElementById("btn-join-queue");

  if (!stationId) {
    showWalkinFeedback("Please choose a destination station.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Joining Queue...";

  try {
    if (!currentCsrfToken) await fetchCsrfToken();

    const payload = {
      station_id: parseInt(stationId, 10),
      driver_name: driverName,
      vehicle_model: vehicleModel,
      vehicle_reg_number: vehicleReg,
      charger_type: chargerType
    };

    const res = await fetch(`${API_BASE}/api/queue/join`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok && data.success) {
      showWalkinFeedback(`🎉 Ticket ${data.ticket.queue_ticket} issued! Switching to live tracker...`, "success");
      setTimeout(() => {
        switchAppTab("my-queue");
      }, 700);
    } else {
      showWalkinFeedback(data.error || "Failed to join walk-in queue.", "error");
    }
  } catch (err) {
    showWalkinFeedback(`Network error: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "⚡ Join Rapid Charging Queue";
  }
}

function showWalkinFeedback(msg, type = "error") {
  const fb = document.getElementById("walkin-feedback");
  if (!fb) return;
  fb.className = `auth-feedback ${type}`;
  fb.textContent = msg;
  fb.style.display = "block";
}

// ============================================================================
// MY BOOKINGS CONTROLLER & POLICIES
// ============================================================================
async function loadMyBookings() {
  const tbody = document.getElementById("my-bookings-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" class="text-center">Loading your reservations...</td></tr>`;

  try {
    const res = await fetch(`${API_BASE}/api/bookings/my`, { credentials: "include" });
    const data = await res.json();

    if (res.ok && data.success) {
      renderMyBookingsTable(data.bookings || []);
    } else {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:var(--accent-red);">${escapeHtml(data.error || "Failed to load bookings.")}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:var(--accent-red);">Network error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderMyBookingsTable(bookings) {
  const tbody = document.getElementById("my-bookings-tbody");
  if (!tbody) return;

  if (bookings.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 2rem; color:var(--text-muted);">You have no charging reservations yet. Click "+ Book New Slot" to reserve your first charging bay.</td></tr>`;
    return;
  }

  tbody.innerHTML = bookings.map(b => {
    let statusClass = "badge-status-confirmed";
    if (b.status === "COMPLETED") statusClass = "badge-status-completed";
    else if (b.status === "CANCELLED") statusClass = "badge-status-cancelled";
    else if (b.status === "MISSED") statusClass = "badge-status-missed";

    let actionBtnHtml = "--";
    if (b.status === "CONFIRMED") {
      if (b.is_cancellable) {
        actionBtnHtml = `<button type="button" class="btn-action-cancel" onclick="handleCancelBookingClick(${b.booking_id})">Cancel</button>`;
      } else {
        actionBtnHtml = `<button type="button" class="btn-action-cancel" disabled title="Cancellation window closed (starts in &lt; 30 mins)">Locked</button>`;
      }
    } else if (b.status === "MISSED") {
      actionBtnHtml = `<button type="button" class="btn-action-alt" onclick="handleOpenAlternativesClick(${b.booking_id})">🔄 Alternatives</button>`;
    }

    return `
      <tr>
        <td><strong>${escapeHtml(b.booking_reference)}</strong></td>
        <td>
          <div style="font-weight:600; color:var(--text-main);">${escapeHtml(b.station_name)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(b.location)}</div>
        </td>
        <td>Port #${b.port_number} (${escapeHtml(b.charger_type)})</td>
        <td>
          <div>${escapeHtml(b.booking_date)}</div>
          <div style="font-weight:600; color:#10b981;">${b.start_time} - ${b.end_time}</div>
        </td>
        <td>${b.duration_minutes} mins</td>
        <td><span class="badge ${statusClass}">${escapeHtml(b.status)}</span></td>
        <td>${actionBtnHtml}</td>
      </tr>
    `;
  }).join("");
}

window.handleCancelBookingClick = async function(bookingId) {
  if (!confirm("Are you sure you want to cancel this booking? The slot will be released back to other drivers.")) {
    return;
  }

  try {
    if (!currentCsrfToken) await fetchCsrfToken();
    const res = await fetch(`${API_BASE}/api/bookings/${bookingId}/cancel`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify({ reason: "Driver requested cancellation" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      alert("Booking successfully cancelled. The reserved slot has been released.");
      loadMyBookings();
    } else {
      alert(data.error || "Failed to cancel booking.");
    }
  } catch (err) {
    alert(`Network error: ${err.message}`);
  }
};

window.handleOpenAlternativesClick = async function(bookingId) {
  const modal = document.getElementById("alternative-modal-backdrop");
  const list = document.getElementById("alt-slots-list");
  if (!modal || !list) return;

  list.innerHTML = `<div class="text-center" style="grid-column: 1/-1; padding: 2rem; color:var(--text-muted);">Finding closest alternative available slots...</div>`;
  modal.style.display = "flex";

  try {
    const res = await fetch(`${API_BASE}/api/bookings/${bookingId}/alternatives`, { credentials: "include" });
    const data = await res.json();

    if (res.ok && data.success) {
      currentMissedBookingOriginal = data.original_booking;
      renderAlternativeSlots(data.alternatives || []);
    } else {
      list.innerHTML = `<div class="auth-feedback error" style="grid-column: 1/-1;">${escapeHtml(data.error || "Failed to find alternatives.")}</div>`;
    }
  } catch (err) {
    list.innerHTML = `<div class="auth-feedback error" style="grid-column: 1/-1;">Network error: ${escapeHtml(err.message)}</div>`;
  }
};

function renderAlternativeSlots(alternatives) {
  const list = document.getElementById("alt-slots-list");
  if (!list) return;

  if (alternatives.length === 0) {
    list.innerHTML = `<div class="text-center" style="grid-column: 1/-1; padding: 2rem; color:var(--text-muted);">No immediate alternative slots available today. Please choose another date in "Book a Slot".</div>`;
    return;
  }

  list.innerHTML = alternatives.map(alt => {
    const isSame = (alt.match_type === "Same Station");
    const badgeClass = isSame ? "alt-badge-same" : "alt-badge-other";

    return `
      <div class="alt-slot-card">
        <div>
          <span class="alt-slot-badge ${badgeClass}">${escapeHtml(alt.match_type)}</span>
          <div class="alt-slot-meta" style="margin-top:0.4rem;">
            <strong>${escapeHtml(alt.station_name)}</strong>
            <span>📍 ${escapeHtml(alt.location || "Hyderabad")}</span>
            <div style="margin-top:0.35rem; font-size:0.85rem; font-weight:600; color:#10b981;">
              📅 ${alt.date} &bull; ${alt.start_time} - ${alt.end_time}
            </div>
            <span style="font-size:0.75rem; color:var(--text-muted);">⚡ ${escapeHtml(alt.charger_type)} &bull; ${alt.duration_minutes} mins</span>
          </div>
        </div>
        <button type="button" class="btn btn-sm btn-primary" onclick="handleRebookSlotConfirm(${alt.station_id}, '${alt.date}', '${alt.start_time}', ${alt.duration_minutes})">
          Rebook This Slot
        </button>
      </div>
    `;
  }).join("");
}

window.handleRebookSlotConfirm = async function(stationId, dateStr, startTime, durationMinutes) {
  if (!currentMissedBookingOriginal) return;

  if (!confirm(`Confirm rebooking this slot at ${dateStr} from ${startTime} (${durationMinutes} mins)?`)) {
    return;
  }

  try {
    if (!currentCsrfToken) await fetchCsrfToken();
    const payload = {
      station_id: stationId,
      driver_name: currentMissedBookingOriginal.driver_name,
      vehicle_model: currentMissedBookingOriginal.vehicle_model,
      vehicle_reg_number: currentMissedBookingOriginal.vehicle_reg_number,
      booking_date: dateStr,
      start_time: startTime,
      duration_minutes: durationMinutes
    };

    const res = await fetch(`${API_BASE}/api/bookings`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (res.ok && data.success) {
      alert(`🎉 Alternative slot booked successfully! Reference: ${data.booking.booking_reference}`);
      document.getElementById("alternative-modal-backdrop").style.display = "none";
      loadMyBookings();
    } else {
      alert(data.error || "Failed to rebook slot.");
    }
  } catch (err) {
    alert(`Network error: ${err.message}`);
  }
};

// ============================================================================
// LIVE QUEUE TRACKER CONTROLLER
// ============================================================================
async function loadMyQueueTicket() {
  const activeContainer = document.getElementById("queue-active-container");
  const emptyContainer = document.getElementById("queue-empty-container");
  const fb = document.getElementById("my-queue-feedback");
  if (fb) fb.style.display = "none";

  try {
    const res = await fetch(`${API_BASE}/api/queue/my`, { credentials: "include" });
    const data = await res.json();

    if (res.ok && data.success && data.ticket) {
      const t = data.ticket;
      activeQueueTicketId = t.queue_id;

      document.getElementById("queue-hero-ticket").textContent = t.queue_ticket;
      document.getElementById("queue-hero-status-badge").textContent = t.status;
      document.getElementById("queue-hero-position").textContent = `#${t.position}`;
      document.getElementById("queue-hero-station").textContent = t.station_name;
      document.getElementById("queue-hero-location").textContent = t.location;
      document.getElementById("queue-hero-wait").textContent = `${t.estimated_wait_minutes} mins`;
      document.getElementById("queue-hero-charger").textContent = t.charger_type;
      document.getElementById("queue-hero-driver").textContent = t.driver_name;
      document.getElementById("queue-hero-vehicle").textContent = `${t.vehicle_model} (${t.vehicle_reg_number})`;

      const subtitle = document.getElementById("queue-hero-pos-desc");
      if (t.position === 1) {
        subtitle.textContent = "You're next in line! Pull up to the charging bay.";
      } else {
        subtitle.textContent = `${t.position - 1} driver(s) ahead of you in the queue.`;
      }

      if (activeContainer) activeContainer.style.display = "block";
      if (emptyContainer) emptyContainer.style.display = "none";
    } else {
      activeQueueTicketId = null;
      if (activeContainer) activeContainer.style.display = "none";
      if (emptyContainer) emptyContainer.style.display = "block";
    }
  } catch (err) {
    console.warn("Could not load queue status:", err);
  }
}

async function handleLeaveQueueSubmit() {
  if (!activeQueueTicketId) return;

  if (!confirm("Are you sure you want to leave the walk-in queue? You will lose your current spot in line.")) {
    return;
  }

  try {
    if (!currentCsrfToken) await fetchCsrfToken();
    const res = await fetch(`${API_BASE}/api/queue/${activeQueueTicketId}/cancel`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": currentCsrfToken
      }
    });

    const data = await res.json();
    if (res.ok && data.success) {
      alert("You have left the queue.");
      loadMyQueueTicket();
    } else {
      alert(data.error || "Failed to leave queue.");
    }
  } catch (err) {
    alert(`Network error: ${err.message}`);
  }
}

// ============================================================================
// ADMIN EXTENDED TABS: BOOKINGS & QUEUES
// ============================================================================
const origSwitchAdminTab = window.switchAdminTab;
window.switchAdminTab = function(tab) {
  const tabOverview = document.getElementById("tab-admin-overview");
  const tabStations = document.getElementById("tab-admin-stations");
  const tabBookings = document.getElementById("tab-admin-bookings");
  const tabQueues = document.getElementById("tab-admin-queues");

  const secOverview = document.getElementById("admin-section-overview");
  const secStations = document.getElementById("admin-section-stations");
  const secBookings = document.getElementById("admin-section-bookings");
  const secQueues = document.getElementById("admin-section-queues");

  [tabOverview, tabStations, tabBookings, tabQueues].forEach(t => t && t.classList.remove("active"));
  [secOverview, secStations, secBookings, secQueues].forEach(s => s && (s.style.display = "none"));

  if (tab === "overview") {
    if (tabOverview) tabOverview.classList.add("active");
    if (secOverview) secOverview.style.display = "block";
    loadAdminOverview();
  } else if (tab === "stations") {
    if (tabStations) tabStations.classList.add("active");
    if (secStations) secStations.style.display = "block";
    loadAdminStations();
  } else if (tab === "bookings") {
    if (tabBookings) tabBookings.classList.add("active");
    if (secBookings) secBookings.style.display = "block";
    loadAdminAllBookings();
  } else if (tab === "queues") {
    if (tabQueues) tabQueues.classList.add("active");
    if (secQueues) secQueues.style.display = "block";
    loadAdminAllQueues();
  }
};

async function loadAdminAllBookings() {
  const tbody = document.getElementById("admin-bookings-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" class="text-center">Loading all user bookings...</td></tr>`;

  try {
    const res = await fetch(`${API_BASE}/api/admin/bookings`, { credentials: "include" });
    const data = await res.json();
    if (res.ok && data.success) {
      const rows = data.bookings || [];
      if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">No bookings found in database.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map(b => `
        <tr>
          <td><strong>${escapeHtml(b.booking_reference)}</strong></td>
          <td>${escapeHtml(b.driver_name)} (${escapeHtml(b.user_email)})</td>
          <td>${escapeHtml(b.station_name)}</td>
          <td>Port #${b.port_number}</td>
          <td>${b.booking_date} ${b.start_time}-${b.end_time}</td>
          <td><span class="badge ${b.status === 'CONFIRMED' ? 'badge-primary' : 'badge-secondary'}">${escapeHtml(b.status)}</span></td>
        </tr>
      `).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--accent-red);">${escapeHtml(data.error || "Failed to load bookings.")}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--accent-red);">Network error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function loadAdminAllQueues() {
  const tbody = document.getElementById("admin-queues-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" class="text-center">Loading all live queues...</td></tr>`;

  try {
    const res = await fetch(`${API_BASE}/api/admin/queues`, { credentials: "include" });
    const data = await res.json();
    if (res.ok && data.success) {
      const rows = data.queues || [];
      if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">No active or recent walk-in tickets.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map(q => `
        <tr>
          <td><strong>${escapeHtml(q.queue_ticket)}</strong></td>
          <td>${escapeHtml(q.driver_name)} (${escapeHtml(q.user_email)})</td>
          <td>${escapeHtml(q.station_name)}</td>
          <td>${escapeHtml(q.vehicle_model)} (${escapeHtml(q.vehicle_reg_number)})</td>
          <td>${escapeHtml(q.joined_at || "--")}</td>
          <td><span class="badge ${q.status === 'WAITING' ? 'badge-primary' : 'badge-secondary'}">${escapeHtml(q.status)}</span></td>
        </tr>
      `).join("");
    } else {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--accent-red);">${escapeHtml(data.error || "Failed to load queues.")}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--accent-red);">Network error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

