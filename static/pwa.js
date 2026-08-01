/* Clustead PWA — 서비스워커 등록 + 홈화면 설치 유도 배너.
 *
 * 안드로이드(크롬): beforeinstallprompt 를 가로채 두었다가 배너의 '설치' 버튼에서
 *   prompt() 호출 → 네이티브 설치 다이얼로그.
 * iOS(사파리): 설치 API 가 없다. '공유 → 홈 화면에 추가' 안내만 노출한다.
 *
 * 배너 노출 정책
 *   · 첫 방문부터 노출(단 첫 화면을 가리지 않게 2.5초 지연)
 *   · 이미 설치된 것으로 확인되면 안 띄움 — standalone 실행 시 플래그를 남겨
 *     이후 일반 브라우저 탭에서도 재노출을 막는다(아래 INSTALLED_KEY 참고)
 *   · 닫으면 90일간 안 띄움
 *   · 인앱 브라우저(네이버·카카오·구글앱 등)는 설치가 불가능하므로 설치 안내
 *     대신 '기본 브라우저로 열기'를 안내
 *   · ?pwa=hint 로 강제 노출(테스트용)
 */
(function () {
    'use strict';

    var VISITS_KEY = 'clustead_visits';
    var DISMISS_KEY = 'clustead_pwa_dismissed_at';
    var INSTALLED_KEY = 'clustead_pwa_installed';
    var DISMISS_DAYS = 90;
    var MIN_VISITS = 1;   // 1 = 첫 방문부터

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
    var isAndroid = /Android/i.test(ua);

    /* 인앱 브라우저(네이버·카카오·구글앱 등)에서는 홈화면 추가가 **불가능**하다.
       iOS 인앱 WebView 엔 '홈 화면에 추가' 메뉴가 없고, 안드로이드 WebView 는
       beforeinstallprompt 가 발생하지 않는다. 검색 유입이 주력이라 모바일
       방문자 상당수가 여기로 들어오므로, 막고 끝내지 말고 '기본 브라우저로
       열기'를 안내해야 설치 경로가 생긴다.
         GSA/  = iOS Google 앱,  '; wv' = 안드로이드 WebView(구글앱 포함)
         NAVER = 네이버 앱,      FB_IAB/FBAN/FBAV = 페이스북 계열 */
    var isInApp = /KAKAOTALK|NAVER|Instagram|FBAN|FBAV|FB_IAB|Line\/|DaumApps|GSA\/|; wv/i.test(ua);

    /* iOS 는 **Safari 에서만** 홈 화면 추가가 된다. iOS 용 Chrome(CriOS)·
       Firefox(FxiOS)·Edge(EdgiOS) 는 껍데기만 다른 WebKit 이라 A2HS 가 없다. */
    var isIOSSafari = isIOS && /Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua) && !isInApp;

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

    /* 설치 완료를 '기억'한다.
       isStandalone() 은 홈화면 아이콘으로 **실행 중일 때만** true 다. 이미 설치한
       사용자가 검색 결과를 타고 일반 브라우저 탭으로 들어오면 false 가 되어
       배너가 다시 뜬다. 그래서 standalone 으로 한 번이라도 실행되면 플래그를
       남겨 이후 브라우저 탭에서도 재노출을 막는다.
       한계: iOS 홈화면 웹앱은 Safari 와 저장소가 분리돼 이 플래그가 공유되지
       않는다. iOS 는 결국 '닫기'(90일)에 의존한다. */
    if (isStandalone()) store(INSTALLED_KEY, '1');

    function shouldOffer() {
        if (force) return true;
        if (isStandalone()) return false;
        if (read(INSTALLED_KEY) === '1') return false;
        if (recentlyDismissed()) return false;
        return visits >= MIN_VISITS;
    }

    /* 이 환경에서 안내할 방식.
         'install'  : 네이티브 설치 프롬프트를 띄울 수 있음(안드로이드 크롬 등)
         'ios-a2hs' : iOS Safari — 공유 → 홈 화면에 추가 안내
         'open-out' : 인앱 브라우저·iOS 비Safari — 설치 불가, 기본 브라우저로 유도
         null       : 안내할 것 없음(데스크톱 등은 beforeinstallprompt 로만 처리) */
    function bannerMode() {
        if (isInApp) return 'open-out';
        if (isIOSSafari) return 'ios-a2hs';
        if (isIOS) return 'open-out';   // iOS Chrome/Firefox 등은 A2HS 불가
        return null;
    }

    /* ---------- 배너 ---------- */
    var deferredPrompt = null;

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();          // 크롬 기본 미니 인포바 억제
        deferredPrompt = e;
        // 첫 방문부터 띄우므로, 착지 직후 화면을 가리지 않게 살짝 늦춘다.
        if (shouldOffer()) setTimeout(function () { showBanner('install'); }, 2500);
    });

    function dismiss(el) {
        store(DISMISS_KEY, String(Date.now()));
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    /* 안드로이드 인앱 WebView 는 intent:// 로 크롬을 직접 띄울 수 있다.
       iOS 는 Safari 를 강제로 여는 공개 스킴이 없어 안내문만 가능하다. */
    function chromeIntentUrl() {
        return 'intent://' + location.host + location.pathname + location.search +
            '#Intent;scheme=https;package=com.android.chrome;end';
    }

    function showBanner(mode) {
        if (!mode || document.getElementById('clusteadPwaBanner')) return;

        var wrap = document.createElement('div');
        wrap.id = 'clusteadPwaBanner';
        wrap.setAttribute('role', 'dialog');
        wrap.setAttribute('aria-label', '홈 화면에 추가');

        var msg, action = '';
        if (mode === 'install') {
            msg = 'Clustead를 홈 화면에 추가하면 앱처럼 바로 열 수 있어요.';
            action = '<button type="button" data-install>설치</button>';
        } else if (mode === 'ios-a2hs') {
            msg = '하단 <b>공유</b> 버튼 → <b>홈 화면에 추가</b> 를 누르면 앱처럼 쓸 수 있어요.';
        } else if (isAndroid) {
            msg = '앱으로 설치하려면 <b>Chrome</b>에서 열어주세요.';
            action = '<a href="' + chromeIntentUrl() + '" data-openout>Chrome으로 열기</a>';
        } else {
            // iOS 인앱/비Safari — 앱마다 메뉴 위치가 달라 일반적인 표현을 쓴다.
            msg = '앱으로 설치하려면 메뉴에서 <b>Safari로 열기</b>를 선택해 주세요.';
        }

        wrap.innerHTML =
            '<img src="/static/icons/icon-192.png" alt="" width="40" height="40">' +
            '<p>' + msg + '</p>' + action +
            '<button type="button" data-close aria-label="닫기">✕</button>';

        document.body.appendChild(wrap);

        wrap.querySelector('[data-close]').addEventListener('click', function () {
            dismiss(wrap);
        });

        var openOut = wrap.querySelector('[data-openout]');
        if (openOut) {
            openOut.addEventListener('click', function () {
                if (typeof window.gtag === 'function') {
                    window.gtag('event', 'pwa_open_in_browser', { ua_kind: 'android_inapp' });
                }
                dismiss(wrap);
            });
        }

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

    /* beforeinstallprompt 가 없는 환경(iOS 전반·인앱 브라우저)은 직접 띄운다. */
    window.addEventListener('load', function () {
        var mode = bannerMode();
        if (mode && shouldOffer()) {
            setTimeout(function () { showBanner(mode); }, 2500);
        }
    });

    /* 설치 완료 로깅 */
    window.addEventListener('appinstalled', function () {
        // 안드로이드·데스크톱은 이 이벤트로 설치를 확정할 수 있다(iOS 는 미발생).
        store(INSTALLED_KEY, '1');
        store(DISMISS_KEY, String(Date.now()));
        if (typeof window.gtag === 'function') {
            window.gtag('event', 'pwa_installed');
        }
    });
})();
