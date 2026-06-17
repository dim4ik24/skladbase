/**
 * SkladBase — мінімальний віджет публічного каталогу (Стадія 4b).
 * Без залежностей (vanilla JS).
 *
 * Приклад вставки на сайт:
 *
 *   <div id="skladbase-catalog"></div>
 *   <script
 *     src="https://your-cdn.example/widget.js"
 *     data-slug="my-shop"
 *     data-base-url="https://api.skladbase.example"
 *     data-target="skladbase-catalog"
 *   ></script>
 *
 * data-slug      — slug магазину (обов'язково)
 * data-base-url  — origin API SkladBase, без кінцевого "/" (обов'язково)
 * data-target    — id контейнера для рендеру (за замовчуванням "skladbase-catalog")
 *
 * Рендерить картки товарів з ціною; для variant.in_stock === false показує
 * бейдж «нема в наявності». Дані беруться лише з GET /api/public/{slug} —
 * публічного read-only ендпоінта без службових полів складу.
 */
(function () {
  "use strict";

  var currentScript = document.currentScript;
  if (!currentScript) {
    console.error("[skladbase-widget] не вдалося визначити <script> тег");
    return;
  }

  var slug = currentScript.getAttribute("data-slug");
  var baseUrl = currentScript.getAttribute("data-base-url");
  var targetId = currentScript.getAttribute("data-target") || "skladbase-catalog";

  if (!slug || !baseUrl) {
    console.error("[skladbase-widget] потрібні атрибути data-slug і data-base-url");
    return;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatAxisValues(axisValues) {
    var keys = Object.keys(axisValues || {});
    if (keys.length === 0) {
      return "";
    }
    return keys
      .map(function (key) {
        return escapeHtml(axisValues[key]);
      })
      .join(" / ");
  }

  function renderVariant(variant) {
    var axisText = formatAxisValues(variant.axis_values);
    var badge = variant.in_stock
      ? ""
      : '<span class="skladbase-badge skladbase-badge--out">нема в наявності</span>';
    return (
      '<div class="skladbase-variant">' +
      (axisText ? '<span class="skladbase-variant-axes">' + axisText + "</span>" : "") +
      '<span class="skladbase-variant-price">' + escapeHtml(variant.price) + "</span>" +
      badge +
      "</div>"
    );
  }

  function renderProduct(product) {
    var variantsHtml = (product.variants || []).map(renderVariant).join("");
    return (
      '<div class="skladbase-product">' +
      '<h3 class="skladbase-product-name">' + escapeHtml(product.name) + "</h3>" +
      '<div class="skladbase-variants">' + variantsHtml + "</div>" +
      "</div>"
    );
  }

  function render(catalog, target) {
    var logo = catalog.logo_url
      ? '<img class="skladbase-shop-logo" src="' + escapeHtml(catalog.logo_url) + '" alt="" />'
      : "";
    var header =
      '<div class="skladbase-shop-header">' +
      logo +
      '<h2 class="skladbase-shop-name" style="color:' + escapeHtml(catalog.accent_color) + '">' +
      escapeHtml(catalog.name) +
      "</h2>" +
      "</div>";

    var productsHtml = (catalog.products || []).map(renderProduct).join("");

    target.innerHTML = header + '<div class="skladbase-products">' + productsHtml + "</div>";
  }

  function renderError(target) {
    target.innerHTML = '<p class="skladbase-error">Каталог тимчасово недоступний.</p>';
  }

  function init() {
    var target = document.getElementById(targetId);
    if (!target) {
      console.error("[skladbase-widget] не знайдено контейнер #" + targetId);
      return;
    }

    var url = baseUrl.replace(/\/+$/, "") + "/api/public/" + encodeURIComponent(slug);

    fetch(url)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (catalog) {
        render(catalog, target);
      })
      .catch(function () {
        renderError(target);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
