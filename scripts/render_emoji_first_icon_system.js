const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "docs", "icon-previews");

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const tones = {
  transport: { bg: "#dbeafe", ring: "#93c5fd", ink: "#1d4ed8", soft: "#eff6ff" },
  education: { bg: "#e0e7ff", ring: "#a5b4fc", ink: "#4338ca", soft: "#eef2ff" },
  convenience: { bg: "#dcfce7", ring: "#86efac", ink: "#15803d", soft: "#f0fdf4" },
  medical: { bg: "#ffe4e6", ring: "#fda4af", ink: "#be123c", soft: "#fff1f2" },
  safety: { bg: "#e2e8f0", ring: "#94a3b8", ink: "#334155", soft: "#f8fafc" },
  rest: { bg: "#dcfce7", ring: "#86efac", ink: "#15803d", soft: "#f0fdf4" },
  culture: { bg: "#f3e8ff", ring: "#d8b4fe", ink: "#7e22ce", soft: "#faf5ff" },
  commerce: { bg: "#fce7f3", ring: "#f9a8d4", ink: "#be185d", soft: "#fdf2f8" },
  activity: { bg: "#ffedd5", ring: "#fdba74", ink: "#c2410c", soft: "#fff7ed" },
  water: { bg: "#cffafe", ring: "#67e8f9", ink: "#0e7490", soft: "#ecfeff" },
  night: { bg: "#ede9fe", ring: "#c4b5fd", ink: "#6d28d9", soft: "#f5f3ff" },
  brand: { bg: "#f1f5f9", ring: "#cbd5e1", ink: "#0f172a", soft: "#ffffff" },
};

const categories = [
  { label: "지하철역", emoji: "🚇", tone: "transport", note: "노선/역" },
  { label: "버스", emoji: "🚌", tone: "transport", note: "간선·지선" },
  { label: "편의점", emoji: "🏪", tone: "convenience", note: "브랜드 우선" },
  { label: "카페", emoji: "☕", tone: "rest", note: "브랜드 우선" },
  { label: "병원", emoji: "🏥", tone: "medical", note: "진료과 칩" },
  { label: "약국", emoji: "💊", tone: "medical", note: "야간·휴일" },
  { label: "학교", emoji: "🏫", tone: "education", note: "배정초" },
  { label: "학원", emoji: "📚", tone: "education", note: "과목별" },
  { label: "공원", emoji: "🌳", tone: "rest", note: "일반/대형" },
  { label: "한강공원", emoji: "🌊", tone: "water", note: "수변" },
  { label: "문화생활", emoji: "🎭", tone: "culture", note: "공연·전시" },
  { label: "상권", emoji: "🌃", tone: "activity", note: "대형/골목" },
  { label: "쇼핑", emoji: "🛍️", tone: "commerce", note: "몰·백화점" },
  { label: "CCTV", emoji: "📹", tone: "safety", note: "방범" },
  { label: "119안전센터", emoji: "🚒", tone: "medical", note: "안전" },
  { label: "유흥주점", emoji: "🍺", tone: "night", note: "제외 조건" },
];

const subtypeGroups = [
  {
    title: "교통",
    chips: [
      { label: "1호선", symbol: "1", tone: "transport", mode: "route", color: "#0052a4" },
      { label: "2호선", symbol: "2", tone: "transport", mode: "route", color: "#00a84d" },
      { label: "간선", symbol: "B", tone: "transport", mode: "route", color: "#2563eb" },
      { label: "지선", symbol: "G", tone: "transport", mode: "route", color: "#16a34a" },
      { label: "광역", symbol: "R", tone: "medical", mode: "route", color: "#dc2626" },
      { label: "심야", symbol: "🌙", tone: "night" },
      { label: "공항", symbol: "✈️", tone: "transport" },
    ],
  },
  {
    title: "병원/학원",
    chips: [
      { label: "내과", symbol: "🩺", tone: "medical" },
      { label: "소아과", symbol: "👶", tone: "medical" },
      { label: "치과", symbol: "🦷", tone: "medical" },
      { label: "안과", symbol: "👁️", tone: "medical" },
      { label: "영어", symbol: "A", tone: "education", mode: "route", color: "#4f46e5" },
      { label: "수학", symbol: "Σ", tone: "education", mode: "route", color: "#4f46e5" },
      { label: "독서실", symbol: "📖", tone: "education" },
    ],
  },
  {
    title: "생활/안전",
    chips: [
      { label: "야간", symbol: "🌙", tone: "night" },
      { label: "주말", symbol: "📅", tone: "convenience" },
      { label: "생활방범", symbol: "🛡️", tone: "safety" },
      { label: "어린이보호", symbol: "🧒", tone: "education" },
      { label: "한강공원", symbol: "🌊", tone: "water" },
      { label: "기타", symbol: "?", tone: "safety", mode: "route", color: "#64748b" },
    ],
  },
];

const brands = [
  { label: "스타벅스", short: "STAR", color: "#00704a" },
  { label: "투썸", short: "A", color: "#d31145" },
  { label: "CU", short: "CU", color: "#642f8f" },
  { label: "GS25", short: "GS25", color: "#0072ce" },
  { label: "세븐일레븐", short: "7", color: "#008061" },
  { label: "이마트", short: "e", color: "#ffd200", ink: "#111827" },
  { label: "코스트코", short: "COST", color: "#005daa" },
  { label: "홈플러스", short: "H", color: "#e31b23" },
];

function shell(width, height, body) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <style>
    .page { fill: #f6f7fb; }
    .title { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 33px; font-weight: 900; fill: #0f172a; }
    .subtitle { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 15px; fill: #475569; }
    .h2 { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 23px; font-weight: 900; fill: #111827; }
    .h3 { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 17px; font-weight: 900; fill: #111827; }
    .body { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 13px; fill: #64748b; }
    .label { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 15px; font-weight: 900; fill: #111827; }
    .small { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 12px; fill: #475569; }
    .emoji { font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif; }
    .brand { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-weight: 900; }
  </style>
  <rect class="page" width="100%" height="100%" />
  <text class="title" x="48" y="54">Emoji-First Icon System</text>
  <text class="subtitle" x="48" y="82">이모지를 대체하지 않고, 생활 인프라의 즉시 인지성을 유지하면서 UI 품질만 올리는 방향입니다.</text>
  ${body}
</svg>`;
}

function panel(x, y, w, h, title, desc, badge) {
  return `
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="22" fill="#ffffff" stroke="#dfe7f2" />
    <text class="h2" x="${x + 28}" y="${y + 42}">${esc(title)}</text>
    <text class="body" x="${x + 28}" y="${y + 66}">${esc(desc)}</text>
    ${badge ? `<rect x="${x + w - 142}" y="${y + 24}" width="110" height="30" rx="15" fill="#ecfeff" stroke="#a5f3fc" /><text class="small" x="${x + w - 87}" y="${y + 44}" text-anchor="middle" font-weight="900" fill="#0e7490">${esc(badge)}</text>` : ""}
  `;
}

function emojiTile(item, x, y, compact = false) {
  const t = tones[item.tone];
  const w = compact ? 168 : 188;
  const h = compact ? 78 : 92;
  return `
    <g>
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="18" fill="#ffffff" stroke="#dde6f2" />
      <rect x="${x + 16}" y="${y + 15}" width="${compact ? 42 : 50}" height="${compact ? 42 : 50}" rx="${compact ? 15 : 17}" fill="${t.bg}" stroke="${t.ring}" stroke-width="1.2" />
      <text class="emoji" x="${x + (compact ? 37 : 41)}" y="${y + (compact ? 43 : 49)}" text-anchor="middle" font-size="${compact ? 24 : 29}">${esc(item.emoji)}</text>
      <text class="label" x="${x + (compact ? 70 : 82)}" y="${y + (compact ? 34 : 38)}">${esc(item.label)}</text>
      <text class="small" x="${x + (compact ? 70 : 82)}" y="${y + (compact ? 55 : 62)}">${esc(item.note)}</text>
    </g>`;
}

function subtypeChip(chip, x, y) {
  const t = tones[chip.tone];
  const w = Math.max(116, 64 + Array.from(chip.label).length * 15);
  const isRoute = chip.mode === "route";
  const fill = chip.color || t.ink;
  return `
    <g>
      <rect x="${x}" y="${y}" width="${w}" height="42" rx="21" fill="#ffffff" stroke="${t.ring}" />
      <rect x="${x + 7}" y="${y + 7}" width="28" height="28" rx="14" fill="${isRoute ? fill : t.bg}" />
      <text class="${isRoute ? "brand" : "emoji"}" x="${x + 21}" y="${y + 27}" text-anchor="middle" font-size="${isRoute ? 13 : 17}" fill="${isRoute ? "#ffffff" : t.ink}">${esc(chip.symbol)}</text>
      <text class="label" x="${x + 44}" y="${y + 27}" font-size="14">${esc(chip.label)}</text>
    </g>`;
}

function brandPill(brand, x, y, w = 174) {
  const ink = brand.ink || "#ffffff";
  return `
    <g>
      <rect x="${x}" y="${y}" width="${w}" height="48" rx="24" fill="#ffffff" stroke="#dde6f2" />
      <rect x="${x + 7}" y="${y + 7}" width="${brand.short.length > 2 ? 58 : 42}" height="34" rx="17" fill="${brand.color}" />
      <text class="brand" x="${x + (brand.short.length > 2 ? 36 : 28)}" y="${y + 29}" text-anchor="middle" font-size="${brand.short.length > 3 ? 10 : 14}" fill="${ink}">${esc(brand.short)}</text>
      <text class="label" x="${x + (brand.short.length > 2 ? 75 : 58)}" y="${y + 30}" font-size="14">${esc(brand.label)}</text>
    </g>`;
}

function mapMarker(item, x, y, size = 74) {
  const t = tones[item.tone];
  const r = size / 2;
  return `
    <g>
      <path d="M${x + r} ${y}c-${r * 0.78} 0-${r} ${r * 0.62}-${r} ${r} 0 ${r * 1.16} ${r} ${size + 15} ${r} ${size + 15}s${r}-${size * 0.84} ${r}-${size + 15}c0-${r * 0.38}-${r * 0.22}-${r}-${r}-${r}Z" fill="${t.ink}" />
      <circle cx="${x + r}" cy="${y + r}" r="${r * 0.7}" fill="#ffffff" opacity="0.96" />
      <text class="emoji" x="${x + r}" y="${y + r + 10}" text-anchor="middle" font-size="${size * 0.43}">${esc(item.emoji)}</text>
      <text class="small" x="${x + r}" y="${y + size + 42}" text-anchor="middle">${esc(item.label)}</text>
    </g>`;
}

function miniResultRow(item, x, y) {
  const t = tones[item.tone];
  return `
    <g>
      <rect x="${x}" y="${y}" width="318" height="62" rx="16" fill="${t.soft}" stroke="${t.ring}" />
      <rect x="${x + 14}" y="${y + 11}" width="40" height="40" rx="14" fill="#ffffff" stroke="${t.ring}" />
      <text class="emoji" x="${x + 34}" y="${y + 39}" text-anchor="middle" font-size="24">${esc(item.emoji)}</text>
      <text class="label" x="${x + 68}" y="${y + 28}">${esc(item.label)}</text>
      <text class="small" x="${x + 68}" y="${y + 47}">기존 이모지 유지 · 위치/크기만 통일</text>
    </g>`;
}

let body = "";

body += panel(
  48,
  112,
  1120,
  328,
  "1. 카테고리는 이모지 타일로 유지",
  "기존보다 나아 보이는 핵심은 아이콘 교체가 아니라 크기, 배경, 여백, 톤을 통일하는 것입니다.",
  "추천 방향",
);
categories.slice(0, 12).forEach((item, index) => {
  const col = index % 6;
  const row = Math.floor(index / 6);
  body += emojiTile(item, 76 + col * 178, 198 + row * 92, true);
});

body += panel(
  48,
  468,
  1120,
  244,
  "2. 서브타입칩은 이모지 + 문자 배지 혼합",
  "버스/지하철은 문자 배지가 더 좋고, 진료과/생활 항목은 이모지가 더 빠르게 읽힙니다.",
  "혼합형",
);
let chipY = 552;
subtypeGroups.forEach((group) => {
  body += `<text class="h3" x="78" y="${chipY + 25}">${esc(group.title)}</text>`;
  let chipX = 178;
  group.chips.forEach((chip) => {
    body += subtypeChip(chip, chipX, chipY, 0);
    chipX += Math.max(116, 64 + Array.from(chip.label).length * 15) + 10;
  });
  chipY += 58;
});

body += panel(
  48,
  740,
  1120,
  236,
  "3. 브랜드는 일반 아이콘 금지, 로고/워드마크 우선",
  "브랜드칩은 이모지도 Lucide도 이길 수 없습니다. 공식 로고가 없을 때만 임시 워드마크를 씁니다.",
  "브랜드 우선",
);
brands.forEach((brand, index) => {
  const col = index % 4;
  const row = Math.floor(index / 4);
  body += brandPill(brand, 80 + col * 264, 826 + row * 66, 210);
});

body += panel(
  48,
  1004,
  1120,
  288,
  "4. Result 지도는 이모지 마커가 더 읽힙니다",
  "지도 위에서는 선 아이콘보다 컬러 핀 + 이모지가 더 빠르게 인지됩니다. 브랜드 POI는 로고 핀으로 분리합니다.",
  "지도 전용",
);
categories.slice(0, 8).forEach((item, index) => {
  body += mapMarker(item, 86 + index * 132, 1092, 68);
});

body += panel(
  48,
  1320,
  1120,
  264,
  "5. Result/Explore 컴포넌트에 들어갔을 때",
  "아이콘을 바꾸는 대신, 한 위치에 고정하고 같은 크기로 감싸면 기존 이모지의 장점이 살아납니다.",
  "UI 예시",
);
categories.slice(0, 6).forEach((item, index) => {
  const col = index % 3;
  const row = Math.floor(index / 3);
  body += miniResultRow(item, 78 + col * 350, 1412 + row * 76);
});

body += `
  <rect x="48" y="1618" width="1120" height="136" rx="22" fill="#0f172a" />
  <text x="78" y="1658" font-family="Malgun Gothic, Segoe UI, Arial" font-size="22" font-weight="900" fill="#ffffff">정리</text>
  <text x="78" y="1692" font-family="Malgun Gothic, Segoe UI, Arial" font-size="15" fill="#dbeafe">이모지보다 나은 범용 아이콘을 찾는 방향은 효율이 낮습니다. 이 화면에서는 이모지를 유지하되, UI 시스템으로 다듬는 쪽이 더 자연스럽습니다.</text>
  <text x="78" y="1720" font-family="Malgun Gothic, Segoe UI, Arial" font-size="15" fill="#dbeafe">추천 조합: 카테고리=이모지 타일, 서브타입=이모지/문자 배지 혼합, 브랜드=공식 로고, 지도=이모지/로고 핀.</text>
`;

fs.mkdirSync(outDir, { recursive: true });
const outPath = path.join(outDir, "05-emoji-first-system.svg");
fs.writeFileSync(outPath, shell(1216, 1792, body), "utf8");
console.log(outPath);
