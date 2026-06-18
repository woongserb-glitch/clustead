const quickButtons = document.querySelectorAll(".quick-search button");
const searchInput = document.querySelector(".search-row input");
const EXPLORE_RESULTS_HASH = "explore-results";

function showPageLoading() {
    const overlay = document.getElementById("homeLoadingOverlay");
    if (overlay) {
        overlay.classList.remove("is-hidden");
    }
}

function hidePageLoading() {
    const overlay = document.getElementById("homeLoadingOverlay");
    if (overlay) {
        overlay.classList.add("is-hidden");
    }
}

function setupHomeLoadingOverlay() {
    const overlay = document.getElementById("homeLoadingOverlay");
    if (!overlay) return;

    // 오버레이 문구는 각 페이지 마크업을 단일 소스로 사용한다.
    window.addEventListener("pageshow", () => {
        hidePageLoading();
    });
}

function hasExploreSearchCriteria(form) {
    const hasValue = (selector) => !!form.querySelector(selector)?.value.trim();
    const hasChecked = (selector) => !!form.querySelector(selector)?.checked;
    const hasAnyChecked = (selector) => Array.from(form.querySelectorAll(selector)).some((input) => input.checked);
    const hasHiddenValue = (selector) => Array.from(form.querySelectorAll(selector)).some((input) => input.value.trim());

    return (
        hasValue('select[name="gu"]')
        || hasValue('select[name="dong"]')
        || hasValue('input[name="assigned_elementary"]')
        || hasValue('input[name="school"]')
        || hasAnyChecked('input[name="area"]')
        || hasValue('select[name="price"]')
        || hasValue('select[name="line"]')
        || hasValue('input[name="station"]')
        || hasValue('select[name="bus_type"]')
        || hasValue('input[name="bus_route"]')
        || hasChecked('input[name="no_nightlife"]')
        || hasHiddenValue('input[type="hidden"][name="priority"]')
    );
}

function collectExploreFormFilters(form) {
    const valueOf = (selector) => form.querySelector(selector)?.value.trim() || "";
    const filters = {};

    [
        ["gu", 'select[name="gu"]'],
        ["dong", 'select[name="dong"]'],
        ["assigned_elementary", 'input[name="assigned_elementary"]'],
        ["school", 'input[name="school"]'],
        ["household", 'select[name="household"]'],
        ["line", 'select[name="line"]'],
        ["station", 'input[name="station"]'],
        ["bus_type", 'select[name="bus_type"]'],
        ["bus_route", 'input[name="bus_route"]'],
    ].forEach(([key, selector]) => {
        const value = valueOf(selector);
        if (value) filters[key] = value;
    });

    const area = Array.from(form.querySelectorAll('input[name="area"]:checked'))
        .map((input) => input.value.trim())
        .filter(Boolean);
    if (area.length) filters.area = area;

    const price = valueOf('select[name="price"]');
    if (price) {
        filters.price = price;
        filters.price_type = valueOf('select[name="price_type"]') || "trade";
    }

    const priority = Array.from(form.querySelectorAll('input[type="hidden"][name="priority"]'))
        .map((input) => input.value.trim())
        .filter(Boolean);
    if (priority.length) filters.priority = priority;

    if (form.querySelector('input[name="no_nightlife"]')?.checked) {
        filters.no_nightlife = "1";
    }

    return filters;
}

function syncExploreShareUrl(form) {
    if (!window.ClusteadShare || !form) return "";
    return window.ClusteadShare.replaceQueryFromFilters(collectExploreFormFilters(form));
}

function setupExploreStateSharing() {
    const form = document.querySelector(".explore-filter-form");
    if (!form || !window.ClusteadShare) return;

    const sync = debounce(() => syncExploreShareUrl(form), 60);
    form.addEventListener("input", sync);
    form.addEventListener("change", sync);
    form.addEventListener("click", (event) => {
        if (event.target.closest(".priority-chip, .priority-remove-btn, [data-priority-add]")) {
            window.setTimeout(() => syncExploreShareUrl(form), 0);
        }
    });
    document.addEventListener("clustead:before-share", () => syncExploreShareUrl(form));
    syncExploreShareUrl(form);
}

function setExploreSubmitFeedback(form, visible) {
    const feedback = form.querySelector("#exploreSubmitFeedback");
    if (!feedback) return;
    feedback.classList.toggle("is-visible", visible);
}

function setupExploreLoading() {
    const form = document.querySelector(".explore-filter-form");
    if (!form) {
        return;
    }
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!hasExploreSearchCriteria(form)) {
            hidePageLoading();
            setExploreSubmitFeedback(form, true);
            form.querySelector("#exploreSubmitFeedback")?.scrollIntoView({ block: "nearest" });
            return;
        }
        showPageLoading();
        // 자유 입력 차단(지하철역·버스번호 등): 후보와 정확히 일치하는 값만 탐색 허용.
        const requireKnown = form.querySelectorAll('[data-autocomplete][data-require-known="true"]');
        for (const input of requireKnown) {
            if (!(await ensureKnownAutocomplete(input))) {
                hidePageLoading();
                return;
            }
        }
        setExploreSubmitFeedback(form, false);
        if (window.ClusteadShare) {
            const encoded = window.ClusteadShare.encodeFilters(collectExploreFormFilters(form));
            if (encoded) {
                const hash = isMobileViewport() ? `#${EXPLORE_RESULTS_HASH}` : "";
                window.location.href = `/explore?q=${encoded}${hash}`;
                return;
            }
        }
        if (isMobileViewport()) {
            form.action = `/explore#${EXPLORE_RESULTS_HASH}`;
        }
        form.submit();
    });
}

function isMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 760px)").matches;
}

function setupExploreResultAnchor() {
    if (window.location.hash !== `#${EXPLORE_RESULTS_HASH}`) return;

    const target = document.getElementById(EXPLORE_RESULTS_HASH);
    if (!target) return;

    window.setTimeout(() => {
        target.scrollIntoView({
            block: "start",
            behavior: isMobileViewport() ? "smooth" : "auto",
        });
        try {
            target.focus({ preventScroll: true });
        } catch (error) {
            target.focus();
        }
    }, 80);
}

quickButtons.forEach((button) => {
    button.addEventListener("click", () => {
        const form = button.closest("form");
        const input = form?.querySelector('[data-autocomplete="apartments"]') || searchInput;
        const value = button.dataset.value || button.textContent.trim();
        if (input) {
            input.value = value;
            input.dataset.selectedValue = value;
            if (form?.dataset.showLoading === "true") {
                showPageLoading();
                form.submit();
            }
        }
    });
});

function debounce(callback, delay = 160) {
    let timer = null;
    return (...args) => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => callback(...args), delay);
    };
}

function closeAllAutocomplete(except = null) {
    document.querySelectorAll(".autocomplete-menu").forEach((menu) => {
        if (menu !== except) {
            const owner = menu.closest(".autocomplete-field")?.querySelector("[data-autocomplete]");
            if (owner) {
                owner.dataset.activeIndex = "-1";
                owner.removeAttribute("aria-activedescendant");
            }
            menu.remove();
        }
    });
}

function createAutocompleteMenu(input) {
    const field = input.closest(".autocomplete-field") || input.parentElement;
    const existingMenu = field.querySelector(".autocomplete-menu");

    closeAllAutocomplete(existingMenu);

    if (existingMenu) {
        input.setAttribute("aria-expanded", "true");
        return existingMenu;
    }

    const menu = document.createElement("div");
    menu.className = "autocomplete-menu";
    menu.setAttribute("role", "listbox");
    input.setAttribute("aria-expanded", "true");
    if (input.dataset.activeIndex === undefined) {
        input.dataset.activeIndex = "-1";
    }
    field.appendChild(menu);
    return menu;
}

function getAutocompleteItems(input) {
    return Array.from(
        input.closest(".autocomplete-field")?.querySelectorAll(".autocomplete-item") || []
    );
}

function setAutocompleteActive(input, nextIndex) {
    const items = getAutocompleteItems(input);
    if (!items.length) return;

    const boundedIndex = (nextIndex + items.length) % items.length;
    input.dataset.activeIndex = String(boundedIndex);

    items.forEach((item, index) => {
        const isActive = index === boundedIndex;
        item.classList.toggle("active", isActive);
        item.setAttribute("aria-selected", isActive ? "true" : "false");
        if (isActive) {
            input.setAttribute("aria-activedescendant", item.id);
            item.scrollIntoView({ block: "nearest" });
        }
    });
}

function setHiddenField(form, name, value) {
    if (!form) return;
    let field = form.querySelector(`input[type="hidden"][name="${name}"]`);
    if (!field) {
        field = document.createElement("input");
        field.type = "hidden";
        field.name = name;
        form.appendChild(field);
    }
    field.value = value || "";
}

function clearAutocompleteIdentity(input) {
    input.dataset.selectedValue = "";
    input.dataset.selectedGu = "";
    input.dataset.selectedDong = "";

    if (input.dataset.autocomplete !== "apartments" || input.dataset.identityPrefix) {
        return;
    }

    const form = input.closest("form");
    setHiddenField(form, "gu", "");
    setHiddenField(form, "dong", "");
}

function selectAutocompleteItem(input, item) {
    if (!item) return false;

    input.value = item.dataset.value;
    input.dataset.selectedValue = item.dataset.value;
    input.dataset.selectedGu = item.dataset.gu || "";
    input.dataset.selectedDong = item.dataset.dong || "";
    input.dataset.activeIndex = "-1";
    input.removeAttribute("aria-activedescendant");
    input.setAttribute("aria-expanded", "false");
    closeAllAutocomplete();
    input.dispatchEvent(new Event("change", { bubbles: true }));

    const form = input.closest("form");
    // Carry the exact (gu, dong) so /result resolves the right complex when
    // apartment names collide across Seoul.
    if (form && input.dataset.autocomplete === "apartments" && !input.dataset.identityPrefix) {
        setHiddenField(form, "gu", item.dataset.gu || "");
        setHiddenField(form, "dong", item.dataset.dong || "");
    }
    if (input.dataset.submitOnSelect === "true" && form) {
        showPageLoading();
        form.submit();
    }
    return true;
}

function autocompleteEndpoint(input, query) {
    const type = input.dataset.autocomplete;
    const params = new URLSearchParams();
    params.set("q", query);

    if (type === "apartments") {
        return `/api/search/apartments?${params.toString()}`;
    }

    if (type === "assigned-elementary") {
        return `/api/search/assigned-elementary?${params.toString()}`;
    }

    if (type === "mid-high-school") {
        return `/api/search/schools?${params.toString()}`;
    }

    if (type === "subway-stations") {
        const lineSource = input.dataset.lineSource;
        const lineElement = lineSource ? document.querySelector(lineSource) : null;
        const line = lineElement?.value || "";
        if (line) {
            params.set("line", line);
        }
        return `/api/search/subway-stations?${params.toString()}`;
    }

    if (type === "bus-routes") {
        const typeSource = input.dataset.busTypeSource;
        const typeElement = typeSource ? document.querySelector(typeSource) : null;
        const busType = typeElement?.value || "";
        if (busType) {
            params.set("type", busType);
        }
        return `/api/search/bus-routes?${params.toString()}`;
    }

    return "";
}

function renderAutocompleteItems(input, menu, items) {
    const previousActiveIndex = Number(input.dataset.activeIndex || "-1");
    menu.innerHTML = "";

    if (!items.length) {
        input.dataset.activeIndex = "-1";
        input.removeAttribute("aria-activedescendant");
        const empty = document.createElement("div");
        empty.className = "autocomplete-empty";
        empty.textContent = "검색 가능한 후보가 없습니다.";
        menu.appendChild(empty);
        return;
    }

    items.forEach((item, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "autocomplete-item";
        button.dataset.value = item.value || item.label || "";
        button.dataset.gu = item.gu || "";
        button.dataset.dong = item.dong || "";
        button.dataset.index = String(index);
        button.id = `${input.name || "autocomplete"}-option-${Date.now()}-${index}`;
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", "false");
        button.innerHTML = `
            <strong>${item.label || item.value || ""}</strong>
            ${item.meta ? `<span>${item.meta}</span>` : ""}
        `;
        let selectionCommitted = false;
        const selectFromPress = (event) => {
            if ((event.type === "pointerdown" || event.type === "mousedown") && event.button > 0) return;
            if (event.cancelable) event.preventDefault();
            event.stopPropagation();
            if (selectionCommitted) return;
            selectionCommitted = true;
            selectAutocompleteItem(input, button);
        };
        button.addEventListener("touchstart", selectFromPress, { passive: false });
        button.addEventListener("pointerdown", selectFromPress);
        button.addEventListener("mousedown", selectFromPress);
        button.addEventListener("click", selectFromPress);
        menu.appendChild(button);
    });

    if (previousActiveIndex >= 0) {
        setAutocompleteActive(input, Math.min(previousActiveIndex, items.length - 1));
    } else {
        input.dataset.activeIndex = "-1";
        input.removeAttribute("aria-activedescendant");
    }
}

async function fetchAutocompleteItems(input) {
    const query = input.value.trim();

    if (query.length < 1) {
        closeAllAutocomplete();
        return;
    }

    const endpoint = autocompleteEndpoint(input, query);
    if (!endpoint) return;

    const menu = createAutocompleteMenu(input);
    const hasVisibleItems = !!menu.querySelector(".autocomplete-item");
    if (!hasVisibleItems) {
        menu.innerHTML = `<div class="autocomplete-empty">검색 중...</div>`;
    }
    const requestId = `${Date.now()}-${Math.random()}`;
    input.dataset.autocompleteRequestId = requestId;

    try {
        const response = await fetch(endpoint);
        const payload = await response.json();
        if (input.dataset.autocompleteRequestId !== requestId) {
            return;
        }
        renderAutocompleteItems(input, menu, payload.items || []);
    } catch (error) {
        if (input.dataset.autocompleteRequestId !== requestId) {
            return;
        }
        menu.innerHTML = `<div class="autocomplete-empty">검색 후보를 불러오지 못했습니다.</div>`;
    }
}

function setupAutocomplete() {
    const inputs = document.querySelectorAll("[data-autocomplete]");

    inputs.forEach((input) => {
        const debouncedFetch = debounce(() => fetchAutocompleteItems(input));

        input.addEventListener("input", () => {
            clearAutocompleteIdentity(input);
            debouncedFetch();
        });

        input.addEventListener("focus", () => {
            if (input.value.trim()) {
                fetchAutocompleteItems(input);
            }
        });

        input.addEventListener("keydown", (event) => {
            const menu = input.closest(".autocomplete-field")?.querySelector(".autocomplete-menu");
            if (event.key === "Escape") {
                closeAllAutocomplete();
                return;
            }

            if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
                event.preventDefault();

                if (!menu) {
                    if (input.value.trim()) {
                        fetchAutocompleteItems(input);
                    }
                    return;
                }

                const items = getAutocompleteItems(input);
                if (!items.length) return;

                const currentIndex = Number(input.dataset.activeIndex || "-1");
                if (event.key === "Home") {
                    setAutocompleteActive(input, 0);
                    return;
                }
                if (event.key === "End") {
                    setAutocompleteActive(input, items.length - 1);
                    return;
                }

                const direction = event.key === "ArrowDown" ? 1 : -1;
                const nextIndex = currentIndex === -1
                    ? (direction === 1 ? 0 : items.length - 1)
                    : currentIndex + direction;

                setAutocompleteActive(input, nextIndex);
                return;
            }

            if (event.key !== "Enter" || !menu) {
                return;
            }

            const items = getAutocompleteItems(input);
            const activeIndex = Number(input.dataset.activeIndex || "-1");
            const selected = items[activeIndex] || items[0];
            if (selected) {
                event.preventDefault();
                selectAutocompleteItem(input, selected);
            }
        });
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".autocomplete-field")) {
            closeAllAutocomplete();
        }
    });
}

function flagAutocompleteInvalid(input, message) {
    input.classList.add("autocomplete-invalid");
    input.setCustomValidity(message || "목록에서 검색 가능한 항목을 선택해주세요.");
    input.reportValidity();
    window.setTimeout(() => {
        input.setCustomValidity("");
        input.classList.remove("autocomplete-invalid");
    }, 1800);
}

// 자유 입력 차단: 자동완성에서 고른 값이거나, 후보와 정확히 일치하는 텍스트만 통과.
// (예: 지하철역에 "종" 한 글자 입력 후 탐색 → 차단)
async function ensureKnownAutocomplete(input) {
    const value = input.value.trim();
    if (!value) return true;                          // 선택형 조건: 비워두면 통과
    if (input.dataset.selectedValue === value) return true;

    const endpoint = autocompleteEndpoint(input, value);
    if (!endpoint) return true;

    try {
        const response = await fetch(endpoint);
        const payload = await response.json();
        const exact = (payload.items || []).find(
            (item) => item.value === value || item.label === value
        );
        if (exact) {
            input.value = exact.value || exact.label;
            input.dataset.selectedValue = input.value;
            // 아파트는 이름이 충돌하므로 식별용 gu/dong도 함께 보관(있을 때만).
            if (exact.gu !== undefined) input.dataset.selectedGu = exact.gu || "";
            if (exact.dong !== undefined) input.dataset.selectedDong = exact.dong || "";
            if (input.dataset.autocomplete === "apartments" && !input.dataset.identityPrefix) {
                const form = input.closest("form");
                setHiddenField(form, "gu", exact.gu || "");
                setHiddenField(form, "dong", exact.dong || "");
            }
            return true;
        }
    } catch (error) {
        return true;                                  // 네트워크 오류 시 탐색을 막지 않음
    }

    flagAutocompleteInvalid(input);
    return false;
}

async function ensureKnownApartment(form) {
    const input = form.querySelector('[data-autocomplete="apartments"][data-require-known="true"]');
    if (!input) {
        return true;
    }

    const value = input.value.trim();
    if (!value) {
        return false;
    }

    if (input.dataset.selectedValue === value) {
        return true;
    }

    try {
        const response = await fetch(`/api/search/apartments?q=${encodeURIComponent(value)}&limit=20`);
        const payload = await response.json();
        const exact = (payload.items || []).find((item) => item.value === value);
        if (exact) {
            input.dataset.selectedValue = exact.value;
            input.value = exact.value;
            input.dataset.selectedGu = exact.gu || "";
            input.dataset.selectedDong = exact.dong || "";
            setHiddenField(form, "gu", exact.gu || "");
            setHiddenField(form, "dong", exact.dong || "");
            return true;
        }
    } catch (error) {
        return true;
    }

    input.classList.add("autocomplete-invalid");
    input.setCustomValidity("검색 가능한 아파트를 선택해주세요.");
    input.reportValidity();
    window.setTimeout(() => {
        input.setCustomValidity("");
        input.classList.remove("autocomplete-invalid");
    }, 1800);
    return false;
}

function setupKnownApartmentForms() {
    document.querySelectorAll("[data-apartment-search-form]").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (form.dataset.showLoading === "true") {
                showPageLoading();
            }
            if (await ensureKnownApartment(form)) {
                form.submit();
            } else if (form.dataset.showLoading === "true") {
                hidePageLoading();
            }
        });
    });
}

function setupCompareForm() {
    const form = document.querySelector("[data-compare-form]");
    if (!form) return;

    const slots = Array.from(
        form.querySelectorAll('[data-autocomplete="apartments"][data-identity-prefix]')
    );

    // 프리필(URL로 들어온 단지)을 dataset에 반영해 재제출 시 식별(gu/dong) 유지.
    slots.forEach((input) => {
        const prefix = input.dataset.identityPrefix;
        if (input.value.trim()) {
            input.dataset.selectedValue = input.value.trim();
            input.dataset.selectedGu = form.querySelector(`input[name="${prefix}_gu"]`)?.value || "";
            input.dataset.selectedDong = form.querySelector(`input[name="${prefix}_dong"]`)?.value || "";
        }
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        for (const input of slots) {
            if (!input.value.trim()) {
                flagAutocompleteInvalid(input, "비교할 단지를 선택해주세요.");
                return;
            }
            if (!(await ensureKnownAutocomplete(input))) {
                return;
            }
        }
        // 단지명이 서울에서 충돌하므로 선택한 단지의 gu/dong을 함께 제출.
        slots.forEach((input) => {
            const prefix = input.dataset.identityPrefix;
            setHiddenField(form, `${prefix}_gu`, input.dataset.selectedGu || "");
            setHiddenField(form, `${prefix}_dong`, input.dataset.selectedDong || "");
        });
        form.submit();
    });
}

function setupDependentDongSelect() {
    const guSelect = document.querySelector("[data-dong-source]");
    const dongSelect = document.querySelector("[data-dong-target]");

    if (!guSelect || !dongSelect) return;

    const loadDongs = async (preserveSelected = true) => {
        const selected = preserveSelected ? dongSelect.dataset.selected || dongSelect.value : "";
        const params = new URLSearchParams();
        if (guSelect.value) {
            params.set("gu", guSelect.value);
        }

        const response = await fetch(`/api/options/dongs?${params.toString()}`);
        const payload = await response.json();
        const items = payload.items || [];

        dongSelect.innerHTML = `<option value="">전체</option>`;
        items.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.value;
            option.textContent = item.label;
            if (selected && item.value === selected) {
                option.selected = true;
            }
            dongSelect.appendChild(option);
        });

        dongSelect.disabled = !guSelect.value;
        if (!guSelect.value) {
            dongSelect.value = "";
        }
    };

    guSelect.addEventListener("change", () => {
        dongSelect.dataset.selected = "";
        dongSelect.value = "";
        loadDongs(false).then(() => {
            dongSelect.dispatchEvent(new Event("change", { bubbles: true }));
        });
    });

    loadDongs(true);
}

function setupSubwayStationDependency() {
    const lineSelect = document.querySelector("[data-subway-line-source]");
    const stationInput = document.querySelector('[data-autocomplete="subway-stations"]');

    if (!lineSelect || !stationInput) return;

    lineSelect.addEventListener("change", () => {
        stationInput.value = "";
        stationInput.dataset.selectedValue = "";
        stationInput.placeholder = lineSelect.value ? `${lineSelect.value} 역 검색` : "노선 선택 후 역 검색";
        closeAllAutocomplete();
    });
}

function getMapContext() {
    return {
        map: window.clusteadMap,
        overlayStorage: window.clusteadOverlayStorage || {}
    };
}

function showAllOverlays() {
    const { map, overlayStorage } = getMapContext();

    if (!map) return;

    if (typeof window.clusteadSetAllCategoryOverlays === "function") {
        window.clusteadSetAllCategoryOverlays();

        if (typeof window.clusteadSetMapLegendAll === "function") {
            window.clusteadSetMapLegendAll();
        }
        return;
    }

    Object.values(overlayStorage).forEach((overlays) => {
        overlays.forEach((overlay) => overlay.setMap(map));
    });

    if (typeof window.clusteadSetMapLegendAll === "function") {
        window.clusteadSetMapLegendAll();
    }
}

function showCategoryOverlays(category) {
    const { map, overlayStorage } = getMapContext();

    if (!map) return;

    const hasCategoryOverlays = Array.isArray(overlayStorage[category]);

    if (!hasCategoryOverlays) {
        showAllOverlays();
        return;
    }

    if (typeof window.clusteadSetCategoryOverlays === "function") {
        Object.keys(overlayStorage).forEach((key) => {
            window.clusteadSetCategoryOverlays(key, key === category);
        });

        if (typeof window.clusteadSetMapLegendForCategory === "function") {
            window.clusteadSetMapLegendForCategory(category);
        }
        return;
    }

    Object.entries(overlayStorage).forEach(([key, overlays]) => {
        overlays.forEach((overlay) => {
            overlay.setMap(key === category ? map : null);
        });
    });

    if (typeof window.clusteadSetMapLegendForCategory === "function") {
        window.clusteadSetMapLegendForCategory(category);
    }
}

function showSubtypeOverlays(category, subtype) {
    const { map, overlayStorage } = getMapContext();

    if (!map) return;

    const hasCategoryOverlays = Array.isArray(overlayStorage[category]);

    if (!hasCategoryOverlays) {
        showAllOverlays();
        return;
    }

    if (typeof window.clusteadSetCategoryOverlays === "function") {
        Object.keys(overlayStorage).forEach((key) => {
            if (key === category && typeof window.clusteadSetSubtypeOverlays === "function") {
                window.clusteadSetSubtypeOverlays(category, subtype);
            } else {
                window.clusteadSetCategoryOverlays(key, false);
            }
        });

        if (typeof window.clusteadSetMapLegendForCategory === "function") {
            window.clusteadSetMapLegendForCategory(category);
        }
        return;
    }

    Object.entries(overlayStorage).forEach(([key, overlays]) => {
        overlays.forEach((overlay) => {
            const overlaySubtype = overlay.clusteadSubtype;
            const overlaySubtypes = Array.isArray(overlay.clusteadSubtypes)
                ? overlay.clusteadSubtypes
                : [];
            const matchesSubtype = (
                overlaySubtype === subtype
                || overlaySubtypes.includes(subtype)
            );

            if (key === category && matchesSubtype) {
                overlay.setMap(map);
            } else {
                overlay.setMap(null);
            }
        });
    });

    if (typeof window.clusteadSetMapLegendForCategory === "function") {
        window.clusteadSetMapLegendForCategory(category);
    }
}

function setupPrioritySearch() {
    const container = document.querySelector("[data-priority-search]");
    if (!container) return;

    const rowsEl = container.querySelector("[data-priority-rows]");
    const addBtn = container.querySelector("[data-priority-add]");
    const options = window.clusteadSubtypeOptions || [];
    if (!options.length) {
        container.style.display = "none";
        return;
    }
    const optByKey = {};
    options.forEach((o) => { optByKey[o.key] = o; });

    function isMultiSelectRow(row) {
        return row.dataset.category === "academy";
    }

    function selectedSubtypes(row) {
        if (!isMultiSelectRow(row)) {
            return row.dataset.subtype ? [row.dataset.subtype] : [];
        }
        try {
            const parsed = JSON.parse(row.dataset.subtypes || "[]");
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            return [];
        }
    }

    function setSelectedSubtypes(row, subtypes) {
        const unique = Array.from(new Set(subtypes.filter(Boolean)));
        row.dataset.subtypes = JSON.stringify(unique);
        row.dataset.subtype = unique[0] || "";
    }

    function takenSubtypes(exceptRow) {
        const set = new Set();
        rowsEl.querySelectorAll(".priority-row").forEach((row) => {
            if (row === exceptRow) return;
            selectedSubtypes(row).forEach((subtype) => set.add(subtype));
        });
        return set;
    }

    function refreshChipStates() {
        rowsEl.querySelectorAll(".priority-row").forEach((row) => {
            const taken = takenSubtypes(row);
            const selected = new Set(selectedSubtypes(row));
            row.querySelectorAll(".priority-chip").forEach((chip) => {
                const sub = chip.dataset.subtype;
                const isSelected = selected.has(sub);
                const disabled = taken.has(sub) && !isSelected;
                chip.classList.toggle("active", isSelected);
                chip.classList.toggle("disabled", disabled);
                chip.disabled = disabled;
            });
        });
    }

    function syncHidden(row) {
        row.querySelectorAll('input[type="hidden"][name="priority"]').forEach((hidden) => {
            hidden.remove();
        });
        if (!row.dataset.category) return;
        selectedSubtypes(row).forEach((subtype) => {
            const hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = "priority";
            hidden.value = `${row.dataset.category}:${subtype}`;
            row.appendChild(hidden);
        });
    }

    function renderChips(row) {
        const chipsWrap = row.querySelector(".priority-chips");
        const helperText = row.querySelector(".priority-helper-text");
        chipsWrap.innerHTML = "";
        if (helperText) {
            helperText.remove();
        }
        const opt = optByKey[row.dataset.category];
        if (!opt) return;
        opt.subtypes.forEach((sub) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "priority-chip";
            chip.dataset.subtype = sub;
            chip.textContent = sub;
            chip.addEventListener("click", () => {
                if (chip.disabled) return;
                if (isMultiSelectRow(row)) {
                    const selected = new Set(selectedSubtypes(row));
                    if (selected.has(sub)) {
                        selected.delete(sub);
                    } else {
                        selected.add(sub);
                    }
                    setSelectedSubtypes(row, Array.from(selected));
                } else {
                    row.dataset.subtype = row.dataset.subtype === sub ? "" : sub;
                    row.dataset.subtypes = "[]";
                }
                syncHidden(row);
                refreshChipStates();
            });
            chipsWrap.appendChild(chip);
        });
        if (opt.helper_text) {
            const helper = document.createElement("p");
            helper.className = "priority-helper-text";
            helper.textContent = opt.helper_text;
            chipsWrap.insertAdjacentElement("afterend", helper);
        }
        refreshChipStates();
    }

    function addRow(initialCat, initialSub) {
        const row = document.createElement("div");
        row.className = "priority-row";
        row.dataset.category = initialCat || "";
        row.dataset.subtype = "";
        row.dataset.subtypes = "[]";
        if (initialCat === "academy") {
            setSelectedSubtypes(row, Array.isArray(initialSub) ? initialSub : [initialSub]);
        } else {
            row.dataset.subtype = Array.isArray(initialSub) ? (initialSub[0] || "") : (initialSub || "");
        }

        const select = document.createElement("select");
        select.className = "priority-cat-select";
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "카테고리 선택";
        select.appendChild(blank);
        options.forEach((o) => {
            const op = document.createElement("option");
            op.value = o.key;
            op.textContent = `${o.icon} ${o.label} (${o.radius_label})`;
            if (o.key === initialCat) op.selected = true;
            select.appendChild(op);
        });
        select.addEventListener("change", () => {
            row.dataset.category = select.value;
            row.dataset.subtype = "";
            row.dataset.subtypes = "[]";
            syncHidden(row);
            renderChips(row);
        });

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "priority-remove-btn";
        removeBtn.setAttribute("aria-label", "우선순위 삭제");
        removeBtn.textContent = "✕";
        removeBtn.addEventListener("click", () => {
            row.remove();
            refreshChipStates();
        });

        const head = document.createElement("div");
        head.className = "priority-row-head";
        head.appendChild(select);
        head.appendChild(removeBtn);

        const chipsWrap = document.createElement("div");
        chipsWrap.className = "priority-chips";

        row.appendChild(head);
        row.appendChild(chipsWrap);
        rowsEl.appendChild(row);

        if (initialCat) {
            renderChips(row);
            if (initialSub) syncHidden(row);
        }
        return row;
    }

    const selected = window.clusteadSelectedPriorities || [];
    if (selected.length) {
        const academySelected = selected
            .filter((p) => p.category === "academy")
            .map((p) => p.subtype);
        if (academySelected.length) {
            addRow("academy", academySelected);
        }
        selected
            .filter((p) => p.category !== "academy")
            .forEach((p) => addRow(p.category, p.subtype));
    } else {
        addRow();
    }
    refreshChipStates();

    addBtn.addEventListener("click", () => addRow());
}

function setupPriceTypeToggle() {
    const wrap = document.querySelector("[data-price-filter]");
    if (!wrap) {
        return;
    }
    const typeSelect = wrap.querySelector("[data-price-type]");
    const bucketSelect = wrap.querySelector("[data-price-bucket]");
    const buckets = window.clusteadPriceBuckets || {};
    if (!typeSelect || !bucketSelect) {
        return;
    }
    typeSelect.addEventListener("change", () => {
        const list = buckets[typeSelect.value] || [];
        bucketSelect.innerHTML = "";
        const all = document.createElement("option");
        all.value = "";
        all.textContent = "전체";
        bucketSelect.appendChild(all);
        list.forEach((bucket) => {
            const opt = document.createElement("option");
            opt.value = bucket.key;
            opt.textContent = bucket.label;
            bucketSelect.appendChild(opt);
        });
        bucketSelect.value = "";
    });
}

document.addEventListener("DOMContentLoaded", () => {
    setupHomeLoadingOverlay();
    setupAutocomplete();
    setupKnownApartmentForms();
    setupDependentDongSelect();
    setupSubwayStationDependency();
    setupPrioritySearch();
    setupPriceTypeToggle();
    setupExploreStateSharing();
    setupExploreLoading();
    setupExploreResultAnchor();
    setupCompareForm();

    const detailCards = document.querySelectorAll(".detail-card");

    detailCards.forEach((card) => {
        const chips = card.querySelectorAll(".subtype-chip");
        const items = card.querySelectorAll("li[data-subtype]");

        let activeSubtype = null;

        chips.forEach((chip) => {
            chip.addEventListener("click", () => {
                const subtype = chip.dataset.subtype;
                const category = card.dataset.category;

                if (activeSubtype === subtype) {
                    activeSubtype = null;

                    chips.forEach((chipItem) => chipItem.classList.remove("active"));
                    items.forEach((item) => {
                        item.style.display = "";
                    });

                    showCategoryOverlays(category);
                    return;
                }

                activeSubtype = subtype;

                chips.forEach((chipItem) => chipItem.classList.remove("active"));
                chip.classList.add("active");

                if (subtype === "__all__") {
                    items.forEach((item) => {
                        item.style.display = "";
                    });

                    showCategoryOverlays(category);
                    return;
                }

                items.forEach((item) => {
                    let subtypes = [];

                    if (item.dataset.subtypes) {
                        try {
                            subtypes = JSON.parse(item.dataset.subtypes);
                        } catch (error) {
                            subtypes = [];
                        }
                    }

                    const matchesSubtype = (
                        item.dataset.subtype === subtype
                        || subtypes.includes(subtype)
                    );

                    item.style.display = matchesSubtype ? "" : "none";
                });

                showSubtypeOverlays(category, subtype);
            });
        });
    });
});

document.addEventListener("DOMContentLoaded", () => {
    const preferenceCards = document.querySelectorAll(".preference-tag[data-category]");
    const detailCards = document.querySelectorAll(".detail-card[data-category]");

    let activeCategory = null;

    preferenceCards.forEach((card) => {
        card.addEventListener("click", () => {
            const category = card.dataset.category;

            if (activeCategory === category) {
                activeCategory = null;

                preferenceCards.forEach((cardItem) => cardItem.classList.remove("active-category"));
                detailCards.forEach((cardItem) => cardItem.classList.remove("active-detail-card"));

                showAllOverlays();
                return;
            }

            document.querySelectorAll(".subtype-chip").forEach((chip) => {
                chip.classList.remove("active");
            });

            document.querySelectorAll("li[data-subtype]").forEach((item) => {
                item.style.display = "";
            });

            activeCategory = category;

            preferenceCards.forEach((cardItem) => cardItem.classList.remove("active-category"));
            card.classList.add("active-category");

            showCategoryOverlays(category);

            detailCards.forEach((cardItem) => {
                cardItem.classList.toggle(
                    "active-detail-card",
                    cardItem.dataset.category === category
                );
            });
        });
    });
});

document.querySelectorAll(".domain-group-card").forEach((domainCard) => {
    const grid = domainCard.querySelector(".domain-category-grid");
    const buttons = domainCard.querySelectorAll(".domain-scroll-btn");

    if (!grid) return;

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            const direction = Number(button.dataset.dir);
            const cardWidth = grid.querySelector(".preference-tag")?.offsetWidth || 140;

            grid.scrollBy({
                left: direction * (cardWidth + 10),
                behavior: "smooth"
            });
        });
    });
});
