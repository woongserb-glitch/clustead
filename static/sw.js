/* Clustead 서비스 워커 — PWA 설치 + 정적자산 캐시 + 오프라인 폴백.
 *
 * 캐시 전략
 *   /static/*  : cache-first  (파일명/쿼리에 버전이 붙어 있어 안전. 재방문 체감속도↑)
 *   내비게이션 : network-first (점수/실거래는 항상 최신이어야 함. 캐시는 오프라인 폴백용)
 *   그 외      : 개입하지 않음(브라우저 기본)
 *
 * 캐시하지 않는 경로: 관리자·API·헬스체크·OG 이미지·엑셀 내보내기·robots/sitemap.
 * 개인화되거나(관리자) 무겁거나(xlsx·OG) 캐시 가치가 없는(healthz) 것들이다.
 *
 * CACHE_VERSION 을 올리면 이전 캐시는 activate 에서 전부 삭제된다.
 * 재배포로 정적 자산이 바뀌면 반드시 올릴 것.
 */
const CACHE_VERSION = 'v7';
const STATIC_CACHE = `clustead-static-${CACHE_VERSION}`;
const PAGE_CACHE = `clustead-pages-${CACHE_VERSION}`;
const OFFLINE_URL = '/static/offline.html';

// 오프라인 폴백에 필요한 최소 자산만 설치 시점에 미리 받는다.
// (style.css 등은 쿼리 버전이 붙어 다녀 런타임 캐시에 맡긴다.)
const PRECACHE = [OFFLINE_URL, '/static/icons/icon-192.png'];

// 오프라인 폴백용 페이지 캐시가 무한정 커지지 않도록 상한을 둔다.
// (가중치 쿼리스트링 조합마다 URL 이 달라져 쌓일 수 있음)
const PAGE_CACHE_MAX = 40;

const NO_CACHE_PREFIXES = ['/admin', '/api', '/og/'];
const NO_CACHE_PATHS = [
  '/healthz',
  '/result/export.xlsx',
  '/robots.txt',
  '/sitemap.xml',
];

function isCacheable(url) {
  if (url.origin !== self.location.origin) return false;
  if (NO_CACHE_PATHS.indexOf(url.pathname) !== -1) return false;
  return !NO_CACHE_PREFIXES.some((p) => url.pathname.startsWith(p));
}

async function trimCache(name, max) {
  const cache = await caches.open(name);
  const keys = await cache.keys();
  // 오래된 것부터 제거(넣은 순서 유지).
  for (let i = 0; i < keys.length - max; i += 1) {
    await cache.delete(keys[i]);
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      // 폴백 자산 하나가 실패해도 설치 자체는 성공시킨다.
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((n) => n !== STATIC_CACHE && n !== PAGE_CACHE)
            .map((n) => caches.delete(n))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return;
  }
  if (!isCacheable(url)) return;

  // 1) 정적 자산 — cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
            }
            return res;
          })
      )
    );
    return;
  }

  // 2) 페이지 내비게이션 — network-first, 실패 시 캐시 → 오프라인 페이지
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(PAGE_CACHE).then((c) =>
              c.put(req, copy).then(() => trimCache(PAGE_CACHE, PAGE_CACHE_MAX))
            );
          }
          return res;
        })
        .catch(() =>
          caches
            .match(req)
            .then((hit) => hit || caches.match(OFFLINE_URL))
        )
    );
  }
});
