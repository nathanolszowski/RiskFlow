/*
 * Visit form: saving on the fly.
 *
 * Each answer is sent by HTMX as soon as it changes (see visit_form_body.html), one request at a time, in order
 * (hx-sync "queue all" on #visit-form). This script adds what HTMX does not do:
 *  - a local copy of every answer not yet confirmed by the server (localStorage), replayed after a network
 *    failure, when the connection comes back, or when the form is opened again;
 *  - the state of the save indicator and the banners (network, expired session, finished visit);
 *  - the +/- buttons of the number fields.
 */
(function () {
  "use strict";

  var root = document.getElementById("visit-form");
  if (!root) return;

  var visitId = root.dataset.visit;
  var saveUrl = root.dataset.saveUrl;
  var storageKey = "visit-" + visitId + "-pending";
  var retryDelay = 3000;
  var retryTimer = null;
  var flushing = false;

  // ---- Pending answers (localStorage, may be unavailable) ----
  function readPending() {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "{}");
    } catch (e) {
      return {};
    }
  }

  function writePending(pending) {
    try {
      if (Object.keys(pending).length) localStorage.setItem(storageKey, JSON.stringify(pending));
      else localStorage.removeItem(storageKey);
    } catch (e) { /* the form still works without the local copy */ }
  }

  function hasPending() {
    return Object.keys(readPending()).length > 0;
  }

  // ---- Indicator and banner ----
  function setStatus(state, text) {
    var status = document.getElementById("save-status");
    if (!status) return;
    status.dataset.state = state;
    var label = status.querySelector("[data-save-text]");
    if (label && text) label.textContent = text;
  }

  function showBanner(text, tone) {
    var banner = document.getElementById("visit-banner");
    if (!banner) return;
    banner.textContent = text;
    banner.className = "px-6 py-2.5 text-center text-sm font-semibold border-b " +
      (tone === "danger"
        ? "bg-status-danger-bg text-status-danger border-status-danger-border"
        : "bg-status-warning-bg text-status-warning border-status-warning-border");
  }

  function hideBanner() {
    var banner = document.getElementById("visit-banner");
    if (banner) banner.className = "hidden";
  }

  function isSaveRequest(detail) {
    var path = (detail.pathInfo && detail.pathInfo.requestPath) ||
      detail.path || (detail.requestConfig && detail.requestConfig.path) || "";
    return path.indexOf(saveUrl) !== -1;
  }

  // ---- Local copy of the answers being sent ----
  document.body.addEventListener("htmx:configRequest", function (event) {
    if (!isSaveRequest(event.detail)) return;
    var params = event.detail.parameters;
    if (!params.field_id) return;
    var pending = readPending();
    pending[params.field_id] = params.value === undefined ? "" : params.value;
    writePending(pending);
    setStatus("saving", "Enregistrement…");
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var detail = event.detail;
    if (!isSaveRequest(detail)) return;

    var params = (detail.requestConfig && detail.requestConfig.parameters) || {};
    var status = detail.xhr ? detail.xhr.status : 0;

    if (status === 200 || status === 422) {
      // Confirmed by the server (or refused for good): the local copy is not needed any more
      var pending = readPending();
      if (params.field_id && pending[params.field_id] === (params.value === undefined ? "" : params.value)) {
        delete pending[params.field_id];
        writePending(pending);
      }
      retryDelay = 3000;
      if (status === 200) {
        hideBanner();
        var card = detail.elt.closest("[data-field-card]");
        if (card) card.removeAttribute("data-invalid");
      } else {
        var invalidCard = detail.elt.closest("[data-field-card]");
        if (invalidCard) invalidCard.setAttribute("data-invalid", "");
        setStatus("saved");
      }
    } else if (status === 401) {
      setStatus("error", "Non enregistré · session expirée");
      showBanner("Votre session a expiré. Reconnectez-vous dans un autre onglet : vos réponses sont conservées sur cet appareil et seront renvoyées.", "danger");
      scheduleRetry();
    } else if (status === 409) {
      var locked = readPending();
      delete locked[params.field_id];
      writePending(locked);
      setStatus("error", "Visite verrouillée");
      showBanner("Cette visite est terminée ou archivée : rechargez la page pour la consulter.", "warning");
    } else {
      // Network failure or server error: keep the local copy and try again
      setStatus("error", "Non enregistré · nouvelle tentative");
      showBanner("Connexion perdue. Vos réponses sont conservées sur cet appareil et seront enregistrées dès que possible.", "warning");
      scheduleRetry();
    }
  });

  // ---- Replay of the pending answers ----
  function scheduleRetry() {
    if (retryTimer) return;
    retryTimer = setTimeout(function () {
      retryTimer = null;
      flushPending();
    }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 60000);
  }

  function flushPending() {
    if (flushing || !window.htmx) return;
    var pending = readPending();
    var ids = Object.keys(pending);
    if (!ids.length) return;
    flushing = true;
    var done = Promise.resolve();
    ids.forEach(function (fieldId) {
      done = done.then(function () {
        var section = root.querySelector('input[name="section_id"]');
        return htmx.ajax("POST", saveUrl, {
          source: root,
          swap: "none",
          values: { field_id: fieldId, value: pending[fieldId], section_id: section ? section.value : "" }
        });
      });
    });
    done.then(function () { flushing = false; }, function () { flushing = false; });
  }

  window.addEventListener("online", flushPending);
  window.addEventListener("beforeunload", function (event) {
    if (hasPending()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.addEventListener("load", flushPending);

  // ---- +/- buttons of the number fields ----
  root.addEventListener("click", function (event) {
    var button = event.target.closest("[data-direction]");
    if (!button) return;
    var stepper = button.closest("[data-stepper]");
    var input = stepper && stepper.querySelector("input");
    if (!input || input.disabled) return;

    var step = parseFloat(stepper.dataset.step) || 1;
    var current = parseFloat(String(input.value).replace(",", "."));
    var value = (isNaN(current) ? 0 : current) + step * parseInt(button.dataset.direction, 10);
    if (stepper.dataset.min !== undefined && value < parseFloat(stepper.dataset.min)) value = parseFloat(stepper.dataset.min);
    if (stepper.dataset.max !== undefined && value > parseFloat(stepper.dataset.max)) value = parseFloat(stepper.dataset.max);
    value = Math.round(value * 1e6) / 1e6;

    input.value = String(value).replace(".", ",");
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
})();
