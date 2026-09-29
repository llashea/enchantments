/* Enchantments Traverse map page.
   MapLibre GL JS 5.24.0 + pmtiles 4.5.0 + protomaps-themes-base 4.5.0: the same
   basemap stack the app ships, reading the same PMTiles extract the data-license
   page offers. Overlays come from the app's own data files in ../data/. */
(function () {
  'use strict';

  var status = document.getElementById('mapStatus');
  function say(text) {
    if (!status) return;
    status.textContent = text || '';
    status.hidden = !text;
  }

  if (!window.maplibregl || !window.pmtiles || !window.protomaps_themes_base) {
    say('The map library did not load. Reload the page.');
    return;
  }

  var DATA = new URL('../data/', window.location.href).href;
  var KM_PER_MILE = 1.609344;
  var SOURCE = 'protomaps';
  var ATTRIBUTION =
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors, ODbL ' +
    '&middot; <a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a> ' +
    '&middot; <a href="../data-license/">Map data and license</a>';

  // The app's paper palette for the protomaps light theme (basemapStyle.ts).
  var PAPER = {
    background: '#F5F8F4', earth: '#E6EBDD', water: '#A9D4DF',
    wood_a: '#D7E2C8', wood_b: '#D1DDC0', scrub_a: '#DFE7D2', scrub_b: '#DAE3CC',
    park_a: '#DDE7D0', park_b: '#D7E2C9',
    landcover: {
      forest: 'rgba(213, 226, 200, 1)', grassland: 'rgba(222, 231, 210, 1)',
      scrub: 'rgba(223, 231, 210, 1)', farmland: 'rgba(228, 232, 214, 1)',
      barren: 'rgba(230, 230, 222, 1)', urban_area: 'rgba(228, 229, 224, 1)',
      glacier: 'rgba(236, 240, 242, 1)'
    },
    city_label: '#4A554B', city_label_halo: '#F5F8F4',
    subplace_label: '#7C877D', subplace_label_halo: '#F5F8F4',
    waterway_label: '#F5F8F4', ocean_label: '#4E7A8A', peak_label: '#5A6A5C'
  };
  var HALO = '#F5F8F4';
  var ROUTE = '#1f6d3a';
  var EIGHTMILE = '#b3702a';
  var TRAILS = '#7c7368';
  var LAKE = '#1B7FA6';
  var ZONE_COLORS = {
    'permit-zone-stuart': '#3b6fb6',
    'permit-zone-colchuck': '#7a4fb3',
    'permit-zone-core-enchantment': '#158f86',
    'permit-zone-snow': '#c2482d',
    'permit-zone-eightmile-caroline': '#b08a2e'
  };
  var LINE_FROM = {
    traverse: 'from Stuart Lake Trailhead along the mapped line',
    'eightmile-lake': 'from Eightmile Trailhead along the Eightmile Lake line',
    'windy-pass': 'from Eightmile Trailhead along the Lake Caroline and Windy Pass line'
  };

  var DASHED_ROADS = ['roads_other', 'roads_minor', 'roads_minor_service',
    'roads_bridges_other', 'roads_bridges_minor', 'roads_tunnels_other', 'roads_tunnels_minor'];

  /* Basemap: the theme layers, post-processed the way the app does it. */
  function basemapLayers() {
    var themed = protomaps_themes_base.layersWithPartialCustomTheme(SOURCE, 'light', PAPER, 'en');
    var out = [];
    themed.forEach(function (raw) {
      var layer = raw;
      if (layer.id === 'pois' || layer.id === 'address_label') return;
      if (layer.layout && ('icon-image' in layer.layout)) {
        var layout = Object.assign({}, layer.layout);
        delete layout['icon-image'];
        layer = Object.assign({}, layer, { layout: layout });
      }
      if (layer.type === 'line' && DASHED_ROADS.indexOf(layer.id) !== -1) {
        layer = Object.assign({}, layer, { paint: Object.assign({}, layer.paint, { 'line-dasharray': [4, 2.5] }) });
      }
      if (layer.id === 'roads_labels_minor') layer = Object.assign({}, layer, { minzoom: 12.5 });
      if (layer.id === 'places_locality') {
        layer = Object.assign({}, layer, {
          layout: Object.assign({}, layer.layout, { 'text-size': ['interpolate', ['linear'], ['zoom'], 6, 11.5, 10, 15] })
        });
      }
      if (layer.id === 'water_stream' && layer.type === 'line') {
        layer = Object.assign({}, layer, {
          minzoom: 11,
          paint: Object.assign({}, layer.paint, {
            'line-width': ['interpolate', ['exponential', 1.4], ['zoom'], 11, 0.7, 14, 1.3, 18, 2.6]
          })
        });
      }
      if (layer.id === 'water_waterway_label') layer = Object.assign({}, layer, { minzoom: 12 });
      out.push(layer);
    });
    // The OSM path network around the route, dashed and muted. Context, not the route.
    out.push({
      id: 'other-trails', type: 'line', source: SOURCE, 'source-layer': 'roads',
      filter: ['in', 'kind', 'other', 'path'], minzoom: 10,
      paint: {
        'line-color': TRAILS, 'line-dasharray': [2, 2],
        'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 10, 0.6, 14, 1.4, 18, 3]
      }
    });
    out.push({
      id: 'other-trails-labels', type: 'symbol', source: SOURCE, 'source-layer': 'roads',
      filter: ['in', 'kind', 'other', 'path'], minzoom: 12,
      layout: {
        'symbol-placement': 'line', 'symbol-spacing': 320,
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 10.5,
        'text-keep-upright': true, 'text-optional': true, 'text-offset': [0, -0.9], 'text-max-angle': 20
      },
      paint: { 'text-color': '#6E655A', 'text-halo-color': HALO, 'text-halo-width': 1.5 }
    });
    return out;
  }

  var protocol = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);

  var map;
  try {
    map = new maplibregl.Map({
      container: 'map',
      style: {
        version: 8,
        glyphs: DATA + 'glyphs/{fontstack}/{range}.pbf',
        sources: {
          protomaps: { type: 'vector', url: 'pmtiles://' + DATA + 'enchantments.pmtiles', attribution: ATTRIBUTION }
        },
        layers: basemapLayers()
      },
      center: [-120.79, 47.51],
      zoom: 11,
      minZoom: 6,
      maxZoom: 17,
      maxBounds: [[-123.35, 45.55], [-119.45, 49.30]],
      attributionControl: false
    });
  } catch (err) {
    say('This browser could not start the map. It needs WebGL. The home page has a static version.');
    return;
  }

  map.addControl(new maplibregl.AttributionControl({ compact: false }), 'bottom-right');
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left');

  map.on('error', function (e) {
    var msg = e && e.error && e.error.message ? e.error.message : String(e);
    if (/pmtiles|enchantments\.pmtiles/i.test(msg)) say('The basemap tiles did not load. The route and zones still draw.');
    console.warn('map:', msg);
  });

  /* Data. */
  function getJSON(name) {
    return fetch(DATA + name).then(function (r) {
      if (!r.ok) throw new Error(name + ' ' + r.status);
      return r.json();
    });
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function feet(m) {
    return (Math.round((m * 3.28084) / 10) * 10).toLocaleString('en-US') + ' ft';
  }
  function miles(km) {
    return (km / KM_PER_MILE).toFixed(1) + ' mi';
  }
  function distanceLine(line, km) {
    return '~' + miles(km) + ' ' + (LINE_FROM[line] || LINE_FROM.traverse) + '. Mapped, not measured.';
  }
  function nearestVertex(vertices, km) {
    var best = null, bestD = Infinity;
    for (var i = 0; i < vertices.length; i++) {
      var d = Math.abs(vertices[i].routeKm - km);
      if (d < bestD) { bestD = d; best = vertices[i]; }
    }
    return best;
  }
  function coords(vertices) {
    return vertices.map(function (v) { return [v.lon, v.lat]; });
  }
  function closeRing(ring) {
    var first = ring[0], last = ring[ring.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) return ring.concat([first]);
    return ring;
  }

  /* Mile markers: the first vertex at or past each whole mile, as the app does.
     Interpolating a prettier position would invent a location. */
  function mileMarkers(vertices) {
    var features = [], n = 0;
    for (var i = 0; i < vertices.length; i++) {
      var v = vertices[i];
      while (v.routeKm >= n * KM_PER_MILE) {
        var value = n;
        n += 1;
        if (value === 0) continue;
        var label = 'Mile ' + value;
        var labelElev = v.elevation == null ? label : label + '\n~' + feet(v.elevation);
        features.push({
          type: 'Feature', id: value,
          properties: { mile: value, label: label, labelElev: labelElev, index: value % 5 === 0 ? 1 : 0 },
          geometry: { type: 'Point', coordinates: [v.lon, v.lat] }
        });
      }
    }
    return { type: 'FeatureCollection', features: features };
  }

  /* A small amber chevron for the passes; drawn here so the style needs no sprite. */
  function passImage() {
    var size = 40, c = document.createElement('canvas');
    c.width = size; c.height = size;
    var ctx = c.getContext('2d');
    ctx.beginPath();
    ctx.moveTo(size / 2, 6); ctx.lineTo(size - 6, size - 8); ctx.lineTo(6, size - 8); ctx.closePath();
    ctx.fillStyle = '#d9962f'; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = '#5a3a0e'; ctx.stroke();
    return ctx.getImageData(0, 0, size, size);
  }

  /* The dam between the Snow Lakes: a short bar with a dark edge. The Forest
     Service's word for it is "the old dam"; AllTrails draws a bridge there. */
  function crossingImage() {
    var size = 40, c = document.createElement('canvas');
    c.width = size; c.height = size;
    var ctx = c.getContext('2d');
    ctx.beginPath();
    ctx.rect(7, 15, size - 14, 10);
    ctx.fillStyle = '#5f8aa6'; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = '#1f3d52'; ctx.stroke();
    return ctx.getImageData(0, 0, size, size);
  }

  /* A small tent for the mapped camping areas, drawn here like the chevron above:
     a triangle, a doorway cut from it, a ground line. One flat colour and a thin
     dark edge so it holds on the pale basemap. */
  function campsiteImage() {
    var size = 40, c = document.createElement('canvas');
    c.width = size; c.height = size;
    var ctx = c.getContext('2d');
    ctx.beginPath();
    ctx.moveTo(size / 2, 5); ctx.lineTo(size - 4, size - 7); ctx.lineTo(4, size - 7); ctx.closePath();
    ctx.fillStyle = '#965a1e'; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = '#4a2c0c'; ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(size / 2, 18); ctx.lineTo(size / 2 + 6, size - 7); ctx.lineTo(size / 2 - 6, size - 7); ctx.closePath();
    ctx.fillStyle = '#ffffff'; ctx.fill();
    return ctx.getImageData(0, 0, size, size);
  }

  function lineFeature(id, name, vertices) {
    return { type: 'Feature', properties: { id: id, name: name }, geometry: { type: 'LineString', coordinates: coords(vertices) } };
  }

  function pointFeature(p, lines) {
    var props = { id: p.id, kind: p.kind, name: p.name, l1: '', l2: '', l3: '' };
    var vertices = lines[p.line] || lines.traverse;
    if (p.kind === 'lake') {
      props.l1 = p.elevationM != null ? 'Elevation ~' + feet(p.elevationM) + ', from OpenStreetMap.' : '';
      props.l2 = distanceLine(p.line, p.routeKm);
      props.l3 = p.availability === 'mapped-non-seasonal'
        ? 'Mapped non-seasonal. Not field verified.'
        : 'Mapped lake. Not field verified.';
    } else {
      var v = nearestVertex(vertices, p.routeKm);
      props.l1 = p.note || '';
      props.l2 = p.routeKm > 0 ? distanceLine(p.line, p.routeKm) : '';
      props.l3 = v && v.elevation != null ? 'Elevation ~' + feet(v.elevation) + ', modeled from a public DEM, not surveyed.' : '';
      if (p.id === 'landmark-aasgard-pass') {
        props.l4 = 'The Forest Service says the pass is often snow covered for most of the year, and with snow it is especially hazardous from hidden rocks, creeks and waterfalls.';
      }
    }
    return { type: 'Feature', properties: props, geometry: { type: 'Point', coordinates: [p.lon, p.lat] } };
  }

  function popupHTML(p) {
    var html = '<p class="popupTitle">' + escapeHTML(p.name) + '</p>';
    ['l1', 'l2', 'l3', 'l4'].forEach(function (k) {
      if (p[k]) html += '<p class="popupLine' + (k === 'l1' && p.kind !== 'lake' ? '' : ' muted') + '">' + escapeHTML(p[k]) + '</p>';
    });
    return html;
  }

  var GROUPS = {
    zones: ['zones-fill', 'zones-line', 'zones-label'],
    lakes: ['lakes-circle', 'lakes-label'],
    miles: ['miles-circle', 'miles-label'],
    eightmile: ['eightmile-casing', 'eightmile-line', 'passes-eightmile'],
    trails: ['other-trails', 'other-trails-labels'],
    contours: ['contours-line', 'contours-index', 'contours-label'],
    shading: ['hillshade-context', 'hillshade-detail'],
    slope: ['slope']
  };
  function setVisible(ids, visible) {
    ids.forEach(function (id) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    });
  }

  function addOverlays(route, eightmile, zones, points) {
    // Terrain shading: the app's own hillshade rasters (ENCHANTMENTSAPP
    // scripts/build-hillshade.py from AWS terrain tiles): a z10 context image
    // across the region and a z12 image over the corridor, the context
    // alpha-holed under the detail so the overlap never double-darkens. Drawn
    // under the water fill and every line so the basemap keeps its labels.
    // Leah on the live page: "shading would be better so you can see
    // higher/lower elev better."
    var HILLSHADE = [
      { id: 'hillshade-context', file: 'enchantments-hillshade-context.png', b: { west: -125.15625, south: 44.590467, east: -117.421875, north: 50.736455 } },
      { id: 'hillshade-detail', file: 'enchantments-hillshade-detail.png', b: { west: -121.201172, south: 47.219568, east: -120.322266, north: 47.813155 } }
    ];
    var styleLayers = map.getStyle().layers;
    var firstLine = styleLayers.filter(function (l) { return l.type === 'line'; })[0];
    var shadeBefore = map.getLayer('water') ? 'water' : (firstLine ? firstLine.id : undefined);
    HILLSHADE.forEach(function (h) {
      map.addSource(h.id, {
        type: 'image', url: DATA + h.file,
        coordinates: [[h.b.west, h.b.north], [h.b.east, h.b.north], [h.b.east, h.b.south], [h.b.west, h.b.south]]
      });
      map.addLayer({ id: h.id, type: 'raster', source: h.id, paint: { 'raster-opacity': 0.55, 'raster-fade-duration': 0 } }, shadeBefore);
    });

    // Slope angle: the app's own band image (ENCHANTMENTSAPP
    // scripts/build-slope.py, the same AWS terrain tiles). Three amber bands
    // where a terrain model about 10 m across says the ground is steeper
    // than 30 degrees, nothing drawn below that. A terrain fact, not a
    // hazard rating; the panel note says so once. Added after the hillshade
    // at the same insertion point, so it sits above the shading and under
    // the water fill and every line. Hidden until its box is ticked. The
    // corners are the generator's slope-bounds.json.
    var SLOPE = { id: 'slope', file: 'enchantments-slope.png', b: { west: -120.959473, south: 47.457809, east: -120.673828, north: 47.635784 } };
    map.addSource(SLOPE.id, {
      type: 'image', url: DATA + SLOPE.file,
      coordinates: [[SLOPE.b.west, SLOPE.b.north], [SLOPE.b.east, SLOPE.b.north], [SLOPE.b.east, SLOPE.b.south], [SLOPE.b.west, SLOPE.b.south]]
    });
    map.addLayer({ id: SLOPE.id, type: 'raster', source: SLOPE.id, layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.6, 'raster-fade-duration': 0 } }, shadeBefore);

    var lines = { traverse: route.trail };
    eightmile.routes.forEach(function (r) { lines[r.id] = r.trail; });

    var firstSymbol = null;
    map.getStyle().layers.some(function (l) { if (l.type === 'symbol') { firstSymbol = l.id; return true; } return false; });

    // Zones: below the basemap's labels, above its ground.
    map.addSource('zones', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: zones.permitZones.map(function (z) {
        return {
          type: 'Feature',
          properties: { id: z.id, label: z.name + ' Zone', color: ZONE_COLORS[z.id] || ROUTE },
          geometry: { type: 'Polygon', coordinates: [closeRing(z.boundary)] }
        };
      }) }
    });
    map.addSource('zone-centroids', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: zones.permitZones.map(function (z) {
        return {
          type: 'Feature',
          properties: { label: z.name + ' Zone', color: ZONE_COLORS[z.id] || ROUTE },
          geometry: { type: 'Point', coordinates: [z.centroid.lon, z.centroid.lat] }
        };
      }) }
    });
    map.addLayer({
      id: 'zones-fill', type: 'fill', source: 'zones',
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.16 }
    }, firstSymbol);
    map.addLayer({
      id: 'zones-line', type: 'line', source: 'zones',
      paint: { 'line-color': ['get', 'color'], 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1, 14, 2], 'line-opacity': 0.85 }
    }, firstSymbol);

    // Lines.
    map.addSource('route', { type: 'geojson', data: { type: 'FeatureCollection', features: [lineFeature('traverse', 'Enchantments Traverse', route.trail)] } });
    map.addSource('eightmile', { type: 'geojson', data: { type: 'FeatureCollection', features: eightmile.routes.map(function (r) { return lineFeature(r.id, r.name, r.trail); }) } });
    map.addLayer({
      id: 'eightmile-casing', type: 'line', source: 'eightmile',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 3, 14, 6.5], 'line-opacity': 0.8 }
    });
    map.addLayer({
      id: 'eightmile-line', type: 'line', source: 'eightmile',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': EIGHTMILE, 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.6, 14, 3.6] }
    });
    map.addLayer({
      id: 'route-casing', type: 'line', source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 9], 'line-opacity': 0.85 }
    });
    map.addLayer({
      id: 'route-line', type: 'line', source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ROUTE, 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 2.2, 14, 5] }
    });

    // Mile markers.
    map.addSource('miles', { type: 'geojson', data: mileMarkers(route.trail) });
    map.addLayer({
      id: 'miles-circle', type: 'circle', source: 'miles', minzoom: 10.5,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10.5, 3, 14, 6],
        'circle-color': '#ffffff', 'circle-stroke-color': ROUTE, 'circle-stroke-width': 1.6
      }
    });
    map.addLayer({
      id: 'miles-label', type: 'symbol', source: 'miles', minzoom: 11.5,
      layout: {
        'text-field': ['step', ['zoom'], ['get', 'label'], 13, ['get', 'labelElev']],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 11.5, 10, 14, 12],
        'text-anchor': 'top', 'text-offset': [0, 0.7], 'text-optional': true, 'text-max-width': 6
      },
      paint: { 'text-color': '#2f4a36', 'text-halo-color': HALO, 'text-halo-width': 1.3 }
    });

    // Points.
    var features = [];
    points.lakes.forEach(function (p) { features.push(pointFeature(Object.assign({ kind: 'lake' }, p), lines)); });
    points.trailheads.forEach(function (p) { features.push(pointFeature(Object.assign({ kind: 'trailhead' }, p), lines)); });
    points.passes.forEach(function (p) { features.push(pointFeature(Object.assign({ kind: 'pass' }, p), lines)); });
    (points.crossings || []).forEach(function (p) { features.push(pointFeature(Object.assign({ kind: 'crossing' }, p), lines)); });
    map.addSource('points', { type: 'geojson', data: { type: 'FeatureCollection', features: features } });

    map.addLayer({
      id: 'lakes-circle', type: 'circle', source: 'points', filter: ['==', ['get', 'kind'], 'lake'], minzoom: 9,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 3.5, 14, 6.5],
        'circle-color': LAKE, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.6
      }
    });
    map.addLayer({
      id: 'lakes-label', type: 'symbol', source: 'points', filter: ['==', ['get', 'kind'], 'lake'], minzoom: 10.5,
      layout: {
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Italic'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 10.5, 10.5, 14, 13],
        'text-variable-anchor': ['left', 'right', 'top', 'bottom'], 'text-radial-offset': 0.7,
        'text-justify': 'auto', 'text-optional': true, 'text-max-width': 8,
        // Lower key places first: the main lake before its "Little" neighbour.
        'symbol-sort-key': ['case', ['in', 'Little', ['get', 'name']], 2, 1]
      },
      paint: { 'text-color': '#175f7c', 'text-halo-color': HALO, 'text-halo-width': 1.4 }
    });

    map.addImage('pass', passImage(), { pixelRatio: 2 });
    map.addImage('crossing', crossingImage(), { pixelRatio: 2 });
    map.addLayer({
      id: 'passes-eightmile', type: 'symbol', source: 'points',
      filter: ['all', ['==', ['get', 'kind'], 'pass'], ['==', ['get', 'id'], 'landmark-windy-pass']], minzoom: 10,
      layout: {
        'icon-image': 'pass', 'icon-size': 0.8, 'icon-allow-overlap': true,
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 10, 10.5, 14, 13],
        'text-anchor': 'top', 'text-offset': [0, 0.9], 'text-optional': true
      },
      paint: { 'text-color': '#7a4d12', 'text-halo-color': HALO, 'text-halo-width': 1.4 }
    });
    map.addLayer({
      id: 'passes-icon', type: 'symbol', source: 'points',
      filter: ['all', ['==', ['get', 'kind'], 'pass'], ['!=', ['get', 'id'], 'landmark-windy-pass']], minzoom: 9,
      layout: {
        'icon-image': 'pass', 'icon-size': 1, 'icon-allow-overlap': true,
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 9, 11, 14, 14],
        'text-anchor': 'top', 'text-offset': [0, 1], 'text-optional': true
      },
      paint: { 'text-color': '#7a4d12', 'text-halo-color': HALO, 'text-halo-width': 1.4 }
    });

    // The dam between the Snow Lakes (points.crossings): the name on the map, the
    // agency's sentence in the popup. Leah, 2026-09-28: "is there a bridge".
    map.addLayer({
      id: 'crossings-icon', type: 'symbol', source: 'points',
      filter: ['==', ['get', 'kind'], 'crossing'], minzoom: 10,
      layout: {
        'icon-image': 'crossing', 'icon-size': 1, 'icon-allow-overlap': true,
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 10, 10.5, 14, 13],
        'text-anchor': 'top', 'text-offset': [0, 0.9], 'text-optional': true
      },
      paint: { 'text-color': '#1f3d52', 'text-halo-color': HALO, 'text-halo-width': 1.4 }
    });

    map.addLayer({
      id: 'trailheads-circle', type: 'circle', source: 'points', filter: ['==', ['get', 'kind'], 'trailhead'], minzoom: 8,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 4, 14, 7.5],
        'circle-color': '#123f27', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2
      }
    });
    map.addLayer({
      id: 'trailheads-label', type: 'symbol', source: 'points', filter: ['==', ['get', 'kind'], 'trailhead'], minzoom: 8.5,
      layout: {
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 8.5, 10.5, 14, 13.5],
        'text-anchor': 'top', 'text-offset': [0, 0.9], 'text-optional': true, 'text-max-width': 8
      },
      paint: { 'text-color': '#123f27', 'text-halo-color': HALO, 'text-halo-width': 1.5 }
    });

    // Zone labels, added last on purpose: MapLibre places symbols from the top-most
    // layer down, so the zone name wins the collision and the lake names move around it
    // (Leah on the live page: "colchuck not clear").
    map.addLayer({
      id: 'zones-label', type: 'symbol', source: 'zone-centroids', minzoom: 9,
      layout: {
        'text-field': ['get', 'label'], 'text-font': ['Noto Sans Medium'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 9, 11, 13, 15],
        'text-letter-spacing': 0.06, 'text-transform': 'uppercase', 'text-max-width': 8
      },
      paint: { 'text-color': ['get', 'color'], 'text-halo-color': HALO, 'text-halo-width': 1.6, 'text-opacity': 0.9 }
    });


    // Popups.
    ['lakes-circle', 'trailheads-circle', 'passes-icon', 'passes-eightmile', 'crossings-icon'].forEach(function (id) {
      map.on('click', id, function (e) {
        var f = e.features && e.features[0];
        if (!f) return;
        new maplibregl.Popup({ maxWidth: '300px', offset: 12 })
          .setLngLat(f.geometry.coordinates)
          .setHTML(popupHTML(f.properties))
          .addTo(map);
      });
      map.on('mouseenter', id, function () { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', id, function () { map.getCanvas().style.cursor = ''; });
    });

    // Camping areas mapped by OpenStreetMap contributors (points.campsites, from
    // the app's campsites.seed.json: tourism=camp_site with backcountry=yes inside
    // a permit zone). Own source and layers so the panel switches them as one.
    // The eight named areas carry the OSM name; the nameless get the tent alone.
    // Inserted under the lake dots on purpose: a lake's or a zone's name wins a
    // collision with a campsite's. The popup says what the mark is and is not, the
    // agency's rule in the app's camping card's own words, the zone as the mapped
    // estimate it is, and the km on the site's own line. Nothing else.
    var CAMP_FROM = {
      traverse: 'from Stuart Lake Trailhead along the mapped line',
      'eightmile-lake': 'from Eightmile Trailhead along the Eightmile Lake line',
      'windy-pass': 'from Eightmile Trailhead along the Lake Caroline and Windy Pass line',
      'trout-creek': 'from Eightmile Trailhead along the Trout Creek line'
    };
    var CAMP_SENTENCES = 'Camping area mapped by OpenStreetMap contributors, not the Forest Service\u2019s designated-site list. ' +
      'Camp only at previously impacted sites \u2014 ground already bare of vegetation.';
    function campsiteFeature(c) {
      var props = {
        id: c.id, kind: 'campsite', name: c.name || 'Mapped campsite', named: !!c.name,
        l1: CAMP_SENTENCES,
        l2: c.zoneName ? 'In the ' + c.zoneName + ' zone (mapped estimate).' : '',
        l3: c.line && c.routeKm != null ? '~' + miles(c.routeKm) + ' ' + (CAMP_FROM[c.line] || CAMP_FROM.traverse) + '.' : ''
      };
      return { type: 'Feature', properties: props, geometry: { type: 'Point', coordinates: [c.lon, c.lat] } };
    }
    map.addImage('campsite', campsiteImage(), { pixelRatio: 2 });
    map.addSource('campsites', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: (points.campsites || []).map(campsiteFeature) }
    });
    map.addLayer({
      id: 'campsites-icon', type: 'symbol', source: 'campsites', minzoom: 10,
      layout: {
        'icon-image': 'campsite', 'icon-anchor': 'bottom', 'icon-allow-overlap': true,
        'icon-size': ['interpolate', ['linear'], ['zoom'], 10, 0.55, 14, 0.85]
      }
    }, 'lakes-circle');
    map.addLayer({
      id: 'campsites-label', type: 'symbol', source: 'campsites', filter: ['==', ['get', 'named'], true], minzoom: 11,
      layout: {
        'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10.5, 14, 12.5],
        'text-anchor': 'top', 'text-offset': [0, 0.3], 'text-optional': true, 'text-max-width': 8
      },
      paint: { 'text-color': '#4a2c0c', 'text-halo-color': HALO, 'text-halo-width': 1.4 }
    }, 'lakes-circle');
    map.on('click', 'campsites-icon', function (e) {
      var f = e.features && e.features[0];
      if (!f) return;
      new maplibregl.Popup({ maxWidth: '300px', offset: 12 })
        .setLngLat(f.geometry.coordinates)
        .setHTML(popupHTML(f.properties))
        .addTo(map);
    });
    map.on('mouseenter', 'campsites-icon', function () { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'campsites-icon', function () { map.getCanvas().style.cursor = ''; });
    GROUPS.campsites = ['campsites-icon', 'campsites-label'];

    // Frame every line, then match the panel's checkboxes.
    var west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
    Object.keys(lines).forEach(function (k) {
      lines[k].forEach(function (v) {
        if (v.lon < west) west = v.lon; if (v.lon > east) east = v.lon;
        if (v.lat < south) south = v.lat; if (v.lat > north) north = v.lat;
      });
    });
    var narrow = window.innerWidth < 700;
    map.fitBounds([[west, south], [east, north]], {
      padding: narrow ? { top: 56, left: 20, right: 20, bottom: 32 } : { top: 40, left: 290, right: 40, bottom: 40 },
      duration: 0
    });
    syncPanel();
  }

  /* Layer panel. */
  var panel = document.getElementById('mapPanel');
  if (panel && window.innerWidth < 700) panel.removeAttribute('open');

  var contoursLoaded = false, contoursLoading = null;
  function ensureContours() {
    if (contoursLoaded) return Promise.resolve();
    if (contoursLoading) return contoursLoading;
    say('Loading contours, about 1 MB…');
    contoursLoading = getJSON('enchantments-contours-ft.json').then(function (fc) {
      var isIndex = ['==', ['%', ['get', 'elevation'], 500], 0];
      map.addSource('contours', { type: 'geojson', data: fc });
      map.addLayer({
        id: 'contours-line', type: 'line', source: 'contours', filter: ['!', isIndex], minzoom: 11,
        paint: { 'line-color': '#8c7a5b', 'line-opacity': 0.4, 'line-width': 0.6 }
      }, 'eightmile-casing');
      map.addLayer({
        id: 'contours-index', type: 'line', source: 'contours', filter: isIndex, minzoom: 10,
        paint: { 'line-color': '#8c7a5b', 'line-opacity': 0.65, 'line-width': 1.1 }
      }, 'eightmile-casing');
      map.addLayer({
        id: 'contours-label', type: 'symbol', source: 'contours', filter: isIndex, minzoom: 12,
        layout: {
          'symbol-placement': 'line', 'symbol-spacing': 320, 'text-max-angle': 25,
          'text-field': ['concat', ['number-format', ['get', 'elevation'], { 'max-fraction-digits': 0 }], ' ft'],
          'text-font': ['Noto Sans Regular'], 'text-size': 10, 'text-keep-upright': true
        },
        paint: { 'text-color': '#6b5a3d', 'text-halo-color': HALO, 'text-halo-width': 1.2 }
      }, 'eightmile-casing');
      contoursLoaded = true;
      say('');
    }).catch(function () {
      say('Contours did not load.');
      contoursLoading = null;
    });
    return contoursLoading;
  }

  function syncPanel() {
    if (!panel) return;
    Array.prototype.forEach.call(panel.querySelectorAll('input[data-layer]'), function (input) {
      var key = input.dataset.layer;
      if (key === 'contours' && !contoursLoaded) { if (input.checked) ensureContours(); return; }
      setVisible(GROUPS[key] || [], input.checked);
    });
  }

  if (panel) {
    panel.addEventListener('change', function (e) {
      var input = e.target;
      if (!input || !input.dataset || !input.dataset.layer) return;
      var key = input.dataset.layer;
      if (key === 'contours' && input.checked && !contoursLoaded) {
        ensureContours().then(function () { setVisible(GROUPS.contours, input.checked); });
        return;
      }
      setVisible(GROUPS[key] || [], input.checked);
    });
  }

  /* Go. */
  var dataReady = Promise.all([
    getJSON('enchantments-route.json'),
    getJSON('enchantments-eightmile.json'),
    getJSON('enchantments-permit-zones.json'),
    getJSON('enchantments-map-points.json')
  ]);
  var mapReady = new Promise(function (resolve) { map.on('load', resolve); });

  Promise.all([dataReady, mapReady]).then(function (r) {
    addOverlays(r[0][0], r[0][1], r[0][2], r[0][3]);
    say('');
  }).catch(function (err) {
    say('Some map data did not load. ' + (err && err.message ? err.message : ''));
    console.warn('map data:', err);
  });
})();
