// Pre-fills the address fields from a suggestion of the address autocompletion.
// Works on content swapped in by HTMX (modals): the listeners are on the document.
(function () {
  function closeSuggestions() {
    document.querySelectorAll("[data-address-suggestions]").forEach(function (list) {
      list.innerHTML = "";
    });
  }

  function setValue(scope, name, value) {
    var input = scope && scope.querySelector('[name="' + name + '"]');
    if (input) {
      input.value = value;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-address-suggestion]");
    if (button) {
      var scope = button.closest("[data-address-fields]");
      var data = button.dataset;
      setValue(scope, "address_line", data.addressLine);
      setValue(scope, "postal_code", data.postalCode);
      setValue(scope, "city", data.city);
      // A single free-text field (starting point of a trip)
      setValue(scope, "origin_address", data.addressLine + ", " + data.postalCode + " " + data.city);
    }
    if (!event.target.closest("input[name='address_line'], input[name='origin_address']")) {
      closeSuggestions();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeSuggestions();
    }
  });
})();
