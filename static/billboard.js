/* Enhance server-rendered content; rankings, numbers and rules stay in HTML. */
(function () {
    'use strict';

    var themeButton = document.querySelector('[data-theme-toggle]');
    var darkPreference = window.matchMedia('(prefers-color-scheme: dark)');
    function isDark() {
        var selected = document.documentElement.dataset.theme;
        return selected ? selected === 'dark' : darkPreference.matches;
    }
    function updateThemeButton() {
        if (!themeButton) return;
        var label = isDark() ? '라이트 모드' : '다크 모드';
        themeButton.textContent = label;
        themeButton.setAttribute('aria-label', label + '로 보기');
    }
    if (themeButton) {
        themeButton.hidden = false;
        updateThemeButton();
        themeButton.addEventListener('click', function () {
            var next = isDark() ? 'light' : 'dark';
            document.documentElement.dataset.theme = next;
            try { localStorage.setItem('clustead-billboard-theme', next); } catch (e) {}
            updateThemeButton();
        });
        if (darkPreference.addEventListener) darkPreference.addEventListener('change', updateThemeButton);
    }

    // A dismissed popover stays closed while its trigger still has focus/hover.
    // No CSS :hover/:focus rule can accidentally reopen it after Escape.
    var popovers = [];
    document.querySelectorAll('[data-rule-wrap]').forEach(function (wrap) {
        var button = wrap.querySelector('[data-rule-button]');
        var popover = wrap.querySelector('[data-rule-pop]');
        var closeButton = wrap.querySelector('[data-rule-close]');
        if (!button || !popover) return;
        var hovered = false;
        var focused = false;
        var pinned = false;
        var dismissed = false;
        function render() {
            var open = !dismissed && (hovered || focused || pinned);
            popover.hidden = !open;
            button.setAttribute('aria-expanded', String(open));
        }
        function dismiss() {
            pinned = false;
            dismissed = true;
            render();
        }
        popovers.push({ wrap: wrap, dismiss: dismiss });
        wrap.dataset.enhanced = 'true';
        button.hidden = false;
        if (closeButton) {
            closeButton.hidden = false;
            closeButton.addEventListener('click', function () {
                button.focus();
                dismiss();
            });
        }
        wrap.addEventListener('pointerenter', function (event) {
            if (event.pointerType !== 'mouse' && event.pointerType !== 'pen') return;
            hovered = true;
            dismissed = false;
            render();
        });
        wrap.addEventListener('pointerleave', function () {
            hovered = false;
            if (!focused) dismissed = false;
            render();
        });
        wrap.addEventListener('focusin', function (event) {
            focused = true;
            if (!wrap.contains(event.relatedTarget)) dismissed = false;
            render();
        });
        wrap.addEventListener('focusout', function (event) {
            if (wrap.contains(event.relatedTarget)) return;
            focused = false;
            pinned = false;
            if (!hovered) dismissed = false;
            render();
        });
        button.addEventListener('click', function () {
            if (pinned && !dismissed) {
                dismiss();
            } else {
                popovers.forEach(function (other) { if (other.wrap !== wrap) other.dismiss(); });
                dismissed = false;
                pinned = true;
                render();
            }
        });
        render();
    });
    document.addEventListener('click', function (event) {
        popovers.forEach(function (entry) {
            if (!entry.wrap.contains(event.target)) entry.dismiss();
        });
    });
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        popovers.forEach(function (entry) {
            if (!entry.wrap.contains(document.activeElement)) {
                entry.dismiss();
                return;
            }
            var trigger = entry.wrap.querySelector('[data-rule-button]');
            if (document.activeElement !== trigger) trigger.focus();
            entry.dismiss();
        });
    });

    var board = document.querySelector('[data-billboard]');
    if (!board) return;
    var slides = Array.from(board.querySelectorAll('[data-slide]'));
    var ticks = Array.from(board.querySelectorAll('[data-slide-target]'));
    var controls = board.querySelector('[data-board-controls]');
    var toggle = board.querySelector('[data-rotation-toggle]');
    var liveRegion = board.querySelector('[data-slides]');
    if (!slides.length || !controls || !toggle) return;
    var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    var current = 0;
    var userPaused = false;
    var hoveredBoard = false;
    var focusedBoard = false;
    var timer = null;

    function show(index) {
        current = (index + slides.length) % slides.length;
        slides.forEach(function (slide, i) {
            slide.hidden = i !== current;
            slide.classList.toggle('is-entering', i === current && !reducedMotion.matches);
        });
        ticks.forEach(function (tick) {
            tick.setAttribute('aria-current', String(tick.dataset.slideTarget === slides[current].id));
        });
    }
    function updateRotation() {
        if (timer !== null) window.clearInterval(timer);
        timer = null;
        var paused = userPaused || hoveredBoard || focusedBoard || reducedMotion.matches || document.hidden;
        toggle.disabled = reducedMotion.matches || slides.length < 2;
        toggle.setAttribute('aria-pressed', String(userPaused || reducedMotion.matches));
        toggle.textContent = reducedMotion.matches ? '자동 전환 꺼짐' : (userPaused ? '자동 전환 시작' : '자동 전환 멈춤');
        liveRegion.setAttribute('aria-live', paused ? 'polite' : 'off');
        if (!paused && slides.length > 1) timer = window.setInterval(function () { show(current + 1); }, 4500);
    }
    ticks.forEach(function (tick) {
        tick.addEventListener('click', function () {
            var index = slides.findIndex(function (slide) { return slide.id === tick.dataset.slideTarget; });
            if (index >= 0) show(index);
            updateRotation();
        });
    });
    toggle.addEventListener('click', function () { userPaused = !userPaused; updateRotation(); });
    board.addEventListener('pointerenter', function (event) {
        if (event.pointerType !== 'mouse' && event.pointerType !== 'pen') return;
        hoveredBoard = true;
        updateRotation();
    });
    board.addEventListener('pointerleave', function () { hoveredBoard = false; updateRotation(); });
    board.addEventListener('focusin', function () { focusedBoard = true; updateRotation(); });
    board.addEventListener('focusout', function (event) {
        if (board.contains(event.relatedTarget)) return;
        focusedBoard = false;
        updateRotation();
    });
    document.addEventListener('visibilitychange', updateRotation);
    if (reducedMotion.addEventListener) reducedMotion.addEventListener('change', updateRotation);
    controls.hidden = slides.length < 2;
    show(0);
    updateRotation();
})();
