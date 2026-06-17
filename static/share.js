(function () {
    "use strict";

    var QUERY_KEY = "q";
    var toastTimer = null;

    function clean(value) {
        return String(value || "").trim();
    }

    function asList(value) {
        if (Array.isArray(value)) {
            return value.map(clean).filter(Boolean);
        }
        value = clean(value);
        return value ? [value] : [];
    }

    function normalizeFilters(filters) {
        filters = filters || {};
        var out = {};
        [
            "gu", "dong", "line", "station", "assigned_elementary", "school",
            "household", "price", "bus_type", "bus_route",
            "no_nightlife"
        ].forEach(function (key) {
            var value = clean(filters[key]);
            if (value) out[key] = value;
        });
        if (out.price) {
            out.price_type = clean(filters.price_type) || "trade";
        }

        var area = asList(filters.area || filters.area_buckets);
        if (area.length) out.area = area;

        var priority = asList(filters.priority || filters.priorities);
        if (priority.length) out.priority = priority;

        return out;
    }

    function hasFilters(filters) {
        return Object.keys(normalizeFilters(filters)).length > 0;
    }

    function encodeBase64Url(text) {
        var bytes = new TextEncoder().encode(text);
        var binary = "";
        bytes.forEach(function (byte) {
            binary += String.fromCharCode(byte);
        });
        return window.btoa(binary)
            .replace(/\+/g, "-")
            .replace(/\//g, "_")
            .replace(/=+$/g, "");
    }

    function decodeBase64Url(value) {
        try {
            var normalized = clean(value).replace(/-/g, "+").replace(/_/g, "/");
            var padding = normalized.length % 4 ? 4 - (normalized.length % 4) : 0;
            var binary = window.atob(normalized + "=".repeat(padding));
            var bytes = new Uint8Array(binary.length);
            for (var i = 0; i < binary.length; i += 1) {
                bytes[i] = binary.charCodeAt(i);
            }
            return new TextDecoder().decode(bytes);
        } catch (error) {
            return "";
        }
    }

    function encodeFilters(filters) {
        var normalized = normalizeFilters(filters);
        if (!Object.keys(normalized).length) return "";
        return encodeBase64Url(JSON.stringify({ v: 1, filters: normalized }));
    }

    function decodeFilters(value) {
        var text = decodeBase64Url(value);
        if (!text) return null;
        try {
            var payload = JSON.parse(text);
            var filters = payload && typeof payload === "object"
                ? (payload.filters || payload)
                : null;
            return filters && typeof filters === "object" ? normalizeFilters(filters) : null;
        } catch (error) {
            return null;
        }
    }

    function filtersFromQuery(search) {
        var params = new URLSearchParams(search || window.location.search);
        var encoded = params.get(QUERY_KEY);
        return encoded ? decodeFilters(encoded) : null;
    }

    function replaceQueryFromFilters(filters, options) {
        options = options || {};
        var encoded = encodeFilters(filters);
        var url = new URL(window.location.href);

        if (encoded) {
            url.search = "";
            url.searchParams.set(QUERY_KEY, encoded);
        } else {
            url.searchParams.delete(QUERY_KEY);
        }

        var nextUrl = url.pathname + url.search + url.hash;
        if (nextUrl !== window.location.pathname + window.location.search + window.location.hash) {
            window.history.replaceState(window.history.state, "", nextUrl);
        }
        return options.absolute ? url.href : nextUrl;
    }

    function showToast(message) {
        var toast = document.querySelector("[data-share-toast]");
        if (!toast) {
            toast = document.createElement("div");
            toast.className = "share-toast";
            toast.dataset.shareToast = "true";
            toast.setAttribute("role", "status");
            toast.setAttribute("aria-live", "polite");
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.classList.add("is-visible");
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            toast.classList.remove("is-visible");
        }, 1800);
    }

    function showFallback(url) {
        var existing = document.querySelector("[data-share-fallback]");
        if (existing) existing.remove();

        var panel = document.createElement("div");
        panel.className = "share-fallback";
        panel.dataset.shareFallback = "true";
        panel.innerHTML = [
            '<div class="share-fallback-head">',
            '<strong>URL을 직접 복사해주세요</strong>',
            '<button type="button" aria-label="닫기">×</button>',
            "</div>",
            '<input type="text" readonly>',
        ].join("");

        var input = panel.querySelector("input");
        input.value = url;
        panel.querySelector("button").addEventListener("click", function () {
            panel.remove();
        });
        document.body.appendChild(panel);
        input.focus();
        input.select();
    }

    async function copyCurrentUrl() {
        document.dispatchEvent(new CustomEvent("clustead:before-share"));
        var url = window.location.href;
        try {
            if (!navigator.clipboard || !navigator.clipboard.writeText) {
                throw new Error("clipboard unavailable");
            }
            await navigator.clipboard.writeText(url);
            showToast("링크를 복사했어요");
        } catch (error) {
            showFallback(url);
        }
    }

    function setupShareButtons() {
        document.querySelectorAll("[data-share-url]").forEach(function (button) {
            button.addEventListener("click", copyCurrentUrl);
        });
    }

    window.ClusteadShare = {
        encodeFilters: encodeFilters,
        decodeFilters: decodeFilters,
        filtersFromQuery: filtersFromQuery,
        hasFilters: hasFilters,
        normalizeFilters: normalizeFilters,
        replaceQueryFromFilters: replaceQueryFromFilters,
        copyCurrentUrl: copyCurrentUrl,
    };

    document.addEventListener("DOMContentLoaded", setupShareButtons);
}());
