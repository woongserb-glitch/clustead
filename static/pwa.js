/* Clustead PWA — 서비스워커 등록 + 홈화면 설치 유도 배너.
 *
 * 안드로이드(크롬): beforeinstallprompt 를 가로채 두었다가 배너의 '설치' 버튼에서
 *   prompt() 호출 → 네이티브 설치 다이얼로그.
 * iOS(사파리): 설치 API 가 없다. '공유 → 홈 화면에 추가' 안내만 노출한다.
 *
 * 배너 노출 정책 — 첫 방문자에게 바로 띄우면 이탈만 는다.
 *   · 이미 설치(standalone)된 상태면 안 띄움
 *   · 2회차 방문부터 노출
 *   · 닫으면 90일간 안 띄움
 *   · 카카오/네이버/인스타 등 인앱 브라우저에서는 안내가 틀리므로 안 띄움
 *   · ?pwa=hint 로 강제 노출(테스트용)
 */
(function () {
    'use strict';

    var VISITS_KEY = 'clustead_visits';
    var DISMISS_KEY = 'clustead_pwa_dismissed_at';
    var DISMISS_DAYS = 90;
    var MIN_VISITS = 2;

    var force = location.search.indexOf('pwa=hint') !== -1;

    /* ---------- 서비스워커 등록 ---------- */
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            // scope '/' 로 등록하려면 서버가 Service-Worker-Allowed: / 를 줘야 한다.
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .catch(function () { /* 등록 실패해도 사이트는 정상 동작 */ });
        });
    }

    /* ---------- 환경 판별 ---------- */
    function isStandalone() {
        try {
            return window.matchMedia('(display-mode: standalone)').matches ||
                window.navigator.standalone === true;
        } catch (e) { return false; }
    }

    var ua = navigator.userAgent || '';
    var isIOS = /iPhone|iPad|iPod/i.test(ua);
    var isInApp = /KAKAOTALK|NAVER|Instagram|FBAN|FBAV|Line\//i.test(ua);

    function store(key, val) {
        try { localStorage.setItem(key, val); } catch (e) { /* 사파리 프라이빗 */ }
    }
    function read(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    /* 방문 횟수 누적 */
    var visits = parseInt(read(VISITS_KEY) || '0', 10) + 1;
    store(VISITS_KEY, String(visits));

    function recentlyDismissed() {
        var at = parseInt(read(DISMISS_KEY) || '0', 10);
        if (!at) return false;
        return (Date.now() - at) < DISMISS_DAYS * 86400000;
    }

    function shouldOffer() {
        if (force) return true;
        if (isStandalone()) return false;
        if (isInApp) return false;
        if (recentlyDismissed()) return false;
        return visits >= MIN_VISITS;
    }

    /* ---------- 배너 ---------- */
    var deferredPrompt = null;

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();          // 크롬 기본 미니 인포바 억제
        deferredPrompt = e;
        if (shouldOffer()) showBanner(false);
    });

    function dismiss(el) {
        store(DISMISS_KEY, String(Date.now()));
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function showBanner(iosMode) {
        if (document.getElementById('clusteadPwaBanner')) return;

        var wrap = document.createElement('div');
        wrap.id = 'clusteadPwaBanner';
        wrap.setAttribute('role', 'dialog');
        wrap.setAttribute('aria-label', '홈 화면에 추가');

        var msg = iosMode
            ? '하단 <b>공유</b> 버튼 → <b>홈 화면에 추가</b> 를 누르면 앱처럼 쓸 수 있어요.'
            : 'Clustead를 홈 화면에 추가하면 앱처럼 바로 열 수 있어요.';

        wrap.innerHTML =
            '<img src="/static/icons/icon-192.png" alt="" width="40" height="40">' +
            '<p>' + msg + '</p>' +
            (iosMode ? '' : '<button type="button" data-install>설치</button>') +
            '<button type="button" data-close aria-label="닫기">✕</button>';

        document.body.appendChild(wrap);

        wrap.querySelector('[data-close]').addEventListener('click', function () {
            dismiss(wrap);
        });

        var installBtn = wrap.querySelector('[data-install]');
        if (installBtn) {
            installBtn.addEventListener('click', function () {
                if (!deferredPrompt) { dismiss(wrap); return; }
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then(function (choice) {
                    if (typeof window.gtag === 'function') {
                        window.gtag('event', 'pwa_install_prompt', {
                            outcome: choice && choice.outcome
                        });
                    }
                    deferredPrompt = null;
                    dismiss(wrap);
                });
            });
        }
    }

    /* iOS 는 beforeinstallprompt 가 없으므로 직접 띄운다. */
    window.addEventListener('load', function () {
        if (isIOS && shouldOffer()) {
            setTimeout(function () { showBanner(true); }, 2500);
        }
    });

    /* 설치 완료 로깅 */
    window.addEventListener('appinstalled', function () {
        store(DISMISS_KEY, String(Date.now()));
        if (typeof window.gtag === 'function') {
            window.gtag('event', 'pwa_installed');
        }
    });
})();
