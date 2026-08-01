/* Clustead PWA — 서비스워커 등록 + 헤더의 '앱 설치' 버튼.
 *
 * 자동 배너는 걷어냈다. 배너는 (a) 한 번 닫으면 사라져 다시 찾을 길이 없고,
 * (b) 설치가 불가능한 인앱 브라우저에서 뜨면 안내가 겉돌았다. 대신 헤더에
 * 상시 노출되는 버튼을 두어, 사용자가 원할 때 스스로 누르게 한다.
 *
 * 버튼을 눌렀을 때 실제로 할 수 있는 일은 환경마다 다르다.
 *   Chrome·Edge (안드로이드·PC) : beforeinstallprompt → 네이티브 설치 다이얼로그(진짜 원클릭)
 *   iOS Safari                 : 설치 API 없음 → '공유 → 홈 화면에 추가' 안내
 *   안드로이드 인앱(네이버 등)   : 설치 불가 → intent:// 로 Chrome 에서 열기
 *   iOS 인앱·iOS 크롬/파폭      : 설치 불가, Safari 전환 스킴도 없음 → 링크 복사
 *   그 외 데스크톱(사파리·파폭)  : 브라우저 메뉴 안내
 *
 * 이미 설치된 것이 확인되면 버튼 자체를 감춘다. ?pwa=hint 로 강제 노출(테스트).
 */
(function () {
    'use strict';

    var INSTALLED_KEY = 'clustead_pwa_installed';
    var force = location.search.indexOf('pwa=hint') !== -1;

    /* ---------- 서비스워커 등록 ---------- */
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            // scope '/' 로 등록하려면 서버가 Service-Worker-Allowed: / 를 줘야 한다.
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .catch(function () { /* 등록 실패해도 사이트는 정상 동작 */ });
        });
    }

    /* ---------- 저장소 ---------- */
    function store(key, val) {
        try { localStorage.setItem(key, val); } catch (e) { /* 사파리 프라이빗 */ }
    }
    function read(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
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
    var isAndroid = /Android/i.test(ua);

    /* 인앱 브라우저에서는 홈화면 추가가 불가능하다. iOS 인앱 WebView 엔 '홈 화면에
       추가' 메뉴가 없고, 안드로이드 WebView 는 beforeinstallprompt 가 없다.
         GSA/  = iOS Google 앱,  '; wv' = 안드로이드 WebView(구글앱 포함)
         NAVER = 네이버 앱,      FB_IAB/FBAN/FBAV = 페이스북 계열 */
    var isInApp = /KAKAOTALK|NAVER|Instagram|FBAN|FBAV|FB_IAB|Line\/|DaumApps|GSA\/|; wv/i.test(ua);

    /* iOS 는 Safari 에서만 홈 화면 추가가 된다. iOS 용 Chrome(CriOS)·Firefox(FxiOS)·
       Edge(EdgiOS) 는 껍데기만 다른 WebKit 이라 A2HS 가 없다. */
    var isIOSSafari = isIOS && /Safari/i.test(ua) &&
        !/CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua) && !isInApp;

    // 설치된 상태로 한 번이라도 실행되면 기억한다. isStandalone() 은 홈화면
    // 아이콘으로 '실행 중일 때만' true 라, 설치자가 일반 탭으로 들어오면
    // false 가 되어 버튼이 다시 보인다.
    // 한계: iOS 홈화면 웹앱은 Safari 와 저장소가 분리돼 이 플래그가 공유되지 않는다.
    if (isStandalone()) store(INSTALLED_KEY, '1');

    function alreadyInstalled() {
        return isStandalone() || read(INSTALLED_KEY) === '1';
    }

    /* ---------- 설치 프롬프트 보관 ---------- */
    var deferredPrompt = null;

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();          // 크롬 기본 미니 인포바 억제
        deferredPrompt = e;
        syncButtons();               // 진짜 설치가 가능해졌으므로 라벨 갱신
    });

    window.addEventListener('appinstalled', function () {
        // 안드로이드·데스크톱은 이 이벤트로 설치를 확정할 수 있다(iOS 는 미발생).
        store(INSTALLED_KEY, '1');
        deferredPrompt = null;
        syncButtons();
        if (typeof window.gtag === 'function') window.gtag('event', 'pwa_installed');
    });

    /* ---------- 버튼 ---------- */
    function buttons() {
        return document.querySelectorAll('[data-pwa-install]');
    }

    function syncButtons() {
        var hide = alreadyInstalled() && !force;
        Array.prototype.forEach.call(buttons(), function (b) { b.hidden = hide; });
    }

    function onInstallClick() {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then(function (choice) {
                if (typeof window.gtag === 'function') {
                    window.gtag('event', 'pwa_install_prompt', {
                        outcome: choice && choice.outcome
                    });
                }
                deferredPrompt = null;
                syncButtons();
            });
            return;
        }
        openGuide();
        if (typeof window.gtag === 'function') {
            window.gtag('event', 'pwa_install_guide', { env: guideKind() });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        syncButtons();
        Array.prototype.forEach.call(buttons(), function (b) {
            b.addEventListener('click', onInstallClick);
        });
    });

    /* ---------- 안내 모달 ---------- */
    function guideKind() {
        if (isIOSSafari) return 'ios-safari';
        if (isInApp && isAndroid) return 'android-inapp';
        if (isInApp || isIOS) return 'ios-out';
        return 'desktop-other';
    }

    function chromeIntentUrl() {
        return 'intent://' + location.host + location.pathname + location.search +
            '#Intent;scheme=https;package=com.android.chrome;end';
    }

    /* iOS 는 Safari 를 여는 공개 스킴이 없다(x-safari- 류는 비공식이라 앱에 따라
       오류 팝업만 뜬다). 확실히 동작하는 행동은 '링크 복사' 뿐이다.
       clipboard API 는 인앱 WebView 에서 막히는 경우가 있어 execCommand 폴백. */
    function copyUrl() {
        var url = location.href;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(url).then(
                function () { return true; },
                function () { return legacyCopy(url); }
            );
        }
        return Promise.resolve(legacyCopy(url));
    }

    function legacyCopy(text) {
        try {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
            document.body.appendChild(ta);
            ta.select();
            ta.setSelectionRange(0, text.length);   // iOS 는 select() 만으로 부족
            var ok = document.execCommand('copy');
            document.body.removeChild(ta);
            return ok;
        } catch (e) { return false; }
    }

    function guideContent(kind) {
        if (kind === 'ios-safari') {
            return {
                title: '홈 화면에 추가',
                body: '<ol class="pwa-steps">' +
                    '<li>하단의 <b>공유</b> 버튼을 누르세요.</li>' +
                    '<li>목록에서 <b>홈 화면에 추가</b>를 선택하세요.</li>' +
                    '<li>오른쪽 위 <b>추가</b>를 누르면 끝입니다.</li>' +
                    '</ol>',
                action: ''
            };
        }
        if (kind === 'android-inapp') {
            return {
                title: 'Chrome에서 열어주세요',
                body: '<p>지금은 앱 안의 브라우저라 설치할 수 없어요. ' +
                    'Chrome으로 열면 바로 설치할 수 있습니다.</p>',
                action: '<a class="pwa-guide-action" href="' + chromeIntentUrl() +
                    '" data-openout>Chrome으로 열기</a>'
            };
        }
        if (kind === 'ios-out') {
            return {
                title: 'Safari에서 열어주세요',
                body: '<p>지금 화면에서는 홈 화면 추가가 안 돼요. ' +
                    '링크를 복사해 <b>Safari</b> 주소창에 붙여넣어 주세요.</p>',
                action: '<button type="button" class="pwa-guide-action" data-copy>링크 복사</button>'
            };
        }
        return {
            title: '앱으로 설치하기',
            body: '<p>주소창 오른쪽의 <b>설치</b> 아이콘, 또는 브라우저 메뉴에서 ' +
                '<b>앱으로 설치</b>를 선택해 주세요. ' +
                'Chrome·Edge에서 가장 잘 동작합니다.</p>',
            action: ''
        };
    }

    function openGuide() {
        closeGuide();
        var kind = guideKind();
        var c = guideContent(kind);

        var back = document.createElement('div');
        back.id = 'clusteadPwaGuide';
        back.innerHTML =
            '<div class="pwa-guide-card" role="dialog" aria-modal="true" aria-label="' + c.title + '">' +
            '<button type="button" class="pwa-guide-close" data-close aria-label="닫기">✕</button>' +
            '<img src="/static/icons/icon-192.png" alt="" width="48" height="48">' +
            '<h2>' + c.title + '</h2>' +
            c.body + c.action +
            '</div>';
        document.body.appendChild(back);

        back.addEventListener('click', function (e) {
            if (e.target === back || e.target.hasAttribute('data-close')) closeGuide();
        });
        document.addEventListener('keydown', escClose);

        var openOut = back.querySelector('[data-openout]');
        if (openOut) {
            openOut.addEventListener('click', function () {
                if (typeof window.gtag === 'function') {
                    window.gtag('event', 'pwa_open_in_browser');
                }
                closeGuide();
            });
        }

        var copyBtn = back.querySelector('[data-copy]');
        if (copyBtn) {
            copyBtn.addEventListener('click', function () {
                copyUrl().then(function (ok) {
                    var p = back.querySelector('.pwa-guide-card p');
                    if (ok) {
                        copyBtn.textContent = '복사됨';
                        if (p) p.innerHTML = '<b>Safari</b>를 열고 주소창에 붙여넣기 하세요.';
                    } else {
                        // 복사조차 막힌 환경 — 주소를 보여줘 손으로 옮기게 한다.
                        copyBtn.textContent = '복사 실패';
                        if (p) p.textContent = location.host + location.pathname;
                    }
                    if (typeof window.gtag === 'function') {
                        window.gtag('event', 'pwa_copy_link', { ok: !!ok });
                    }
                });
            });
        }
    }

    function escClose(e) { if (e.key === 'Escape') closeGuide(); }

    function closeGuide() {
        var el = document.getElementById('clusteadPwaGuide');
        if (el && el.parentNode) el.parentNode.removeChild(el);
        document.removeEventListener('keydown', escClose);
    }
})();
