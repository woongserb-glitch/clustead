/* 전 페이지 공통 다크/라이트 전환(2026-10-02). 선택은 'clustead-theme'에 저장되어 페이지를 옮겨도 유지된다.
   첫 화면 깜빡임을 막는 초기값 설정은 _theme_head.html 이 <head> 에서 먼저 한다. */
(function () {
    'use strict';
    var KEY = 'clustead-theme';
    var root = document.documentElement;
    var darkPreference = window.matchMedia('(prefers-color-scheme: dark)');
    function isDark() {
        var selected = root.dataset.theme;
        return selected ? selected === 'dark' : darkPreference.matches;
    }
    function sync(button) {
        var label = isDark() ? '라이트 모드' : '다크 모드';
        // 폰에서는 메뉴 줄이 늘지 않게 아이콘만 보인다(글자는 brand.css 가 숨김).
        button.innerHTML = '<span class="site-theme-icon" aria-hidden="true">' + (isDark() ? '☀︎' : '☾') + '</span><span class="site-theme-label">' + label + '</span>';
        button.setAttribute('aria-label', label + '로 보기');
    }
    document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
        button.hidden = false;
        sync(button);
        button.addEventListener('click', function () {
            var next = isDark() ? 'light' : 'dark';
            root.dataset.theme = next;
            try { localStorage.setItem(KEY, next); } catch (e) {}
            document.querySelectorAll('[data-theme-toggle]').forEach(sync);
            document.dispatchEvent(new CustomEvent('clustead:themechange', { detail: { theme: next } }));
        });
        if (darkPreference.addEventListener) darkPreference.addEventListener('change', function () { sync(button); });
    });
})();
