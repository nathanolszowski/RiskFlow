// Shows a Leaflet map with the Géoplateforme (IGN) plan for every [data-address-map].
// data-lat / data-lon / data-label: the place; data-origin-*: optional starting point.
(function () {
  var TILES =
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
    "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png" +
    "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";

  function popup(text) {
    return document.createTextNode(text || "");
  }

  function init(root) {
    if (!window.L) {
      return;
    }
    (root || document).querySelectorAll("[data-address-map]:not([data-ready])").forEach(function (el) {
      var lat = parseFloat(el.dataset.lat);
      var lon = parseFloat(el.dataset.lon);
      if (isNaN(lat) || isNaN(lon)) {
        return;
      }
      el.dataset.ready = "1";
      var map = L.map(el, { scrollWheelZoom: false }).setView([lat, lon], 15);
      L.tileLayer(TILES, { maxZoom: 18, attribution: "© IGN" }).addTo(map);
      var points = [[lat, lon]];
      L.marker([lat, lon]).addTo(map).bindPopup(popup(el.dataset.label));
      var originLat = parseFloat(el.dataset.originLat);
      var originLon = parseFloat(el.dataset.originLon);
      if (!isNaN(originLat) && !isNaN(originLon)) {
        L.circleMarker([originLat, originLon], { radius: 7 }).addTo(map).bindPopup(popup(el.dataset.originLabel));
        points.push([originLat, originLon]);
      }
      if (points.length > 1) {
        map.fitBounds(points, { padding: [30, 30] });
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    init();
  });
  // Content swapped in by HTMX (tabs, edited cards)
  document.addEventListener("htmx:afterSettle", function (event) {
    init(event.target);
  });
})();
