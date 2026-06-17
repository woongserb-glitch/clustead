const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "docs", "icon-previews");

function loadLucide() {
  const candidates = [
    "lucide",
    process.env.LUCIDE_CJS_PATH,
    process.env.USERPROFILE
      ? path.join(
          process.env.USERPROFILE,
          ".cache",
          "codex-runtimes",
          "codex-primary-runtime",
          "dependencies",
          "node",
          "node_modules",
          "lucide",
          "dist",
          "cjs",
          "lucide.js",
        )
      : null,
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // Try the next known runtime location.
    }
  }
  throw new Error("Lucide package was not found.");
}

const lucide = loadLucide();

const colors = {
  transport: "#2563eb",
  convenience: "#059669",
  medical: "#e11d48",
  education: "#4f46e5",
  safety: "#475569",
  rest: "#16a34a",
  culture: "#7c3aed",
  activity: "#d97706",
  commerce: "#db2777",
  hangang: "#0891b2",
  nightlife: "#9333ea",
};

const samples = [
  { label: "지하철역", emoji: "🚇", icon: "train-front", tone: "transport" },
  { label: "버스", emoji: "🚌", icon: "bus-front", tone: "transport" },
  { label: "카페", emoji: "☕", icon: "coffee", tone: "rest" },
  { label: "병원", emoji: "🏥", icon: "hospital", tone: "medical" },
  { label: "학원", emoji: "📚", icon: "book-open-check", tone: "education" },
  { label: "CCTV", emoji: "📹", icon: "cctv", tone: "safety" },
  { label: "한강공원", emoji: "🌊", icon: "droplets", tone: "hangang" },
  { label: "유흥주점", emoji: "🍺", icon: "martini", tone: "nightlife" },
];

const chips = [
  { label: "간선", emoji: "B", icon: "bus-front", tone: "transport" },
  { label: "치과", emoji: "🦷", icon: "smile-plus", tone: "medical" },
  { label: "입시/보습", emoji: "📚", icon: "book-open-check", tone: "education" },
  { label: "한강공원", emoji: "🌊", icon: "droplets", tone: "hangang" },
  { label: "기타", emoji: "?", icon: "circle-question-mark", tone: "safety" },
];

const brands = [
  { label: "스타벅스", short: "STAR", color: "#00704a" },
  { label: "CU", short: "CU", color: "#642f8f" },
  { label: "GS25", short: "GS25", color: "#0072ce" },
  { label: "이마트", short: "e", color: "#f4c400", ink: "#111827" },
  { label: "코스트코", short: "COST", color: "#005daa" },
];

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pascalIconName(iconName) {
  return String(iconName)
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

function attrsToString(attrs) {
  return Object.entries(attrs || {})
    .map(([key, value]) => ` ${key}="${esc(value)}"`)
    .join("");
}

function lucideIcon(iconName, x, y, size, color = "#334155", strokeWidth = 2.15) {
  const key = pascalIconName(iconName);
  const iconNode = lucide.icons?.[key] || lucide[key];
  if (!iconNode) return "";
  const scale = size / 24;
  const nodes = iconNode.map(([tag, attrs]) => `<${tag}${attrsToString(attrs)} />`).join("");
  return `
    <g transform="translate(${x} ${y}) scale(${scale})" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round">
      ${nodes}
    </g>`;
}

function shell(width, height, body) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <style>
    .bg { fill: #f8fafc; }
    .title { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 32px; font-weight: 900; fill: #0f172a; }
    .subtitle { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 15px; fill: #475569; }
    .h2 { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 21px; font-weight: 900; fill: #111827; }
    .desc { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 13px; fill: #64748b; }
    .label { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 16px; font-weight: 800; fill: #111827; }
    .small { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 12px; fill: #475569; }
    .tiny { font-family: "Segoe UI", Arial, sans-serif; font-size: 10px; fill: #64748b; }
    .emoji { font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif; }
  </style>
  <rect class="bg" width="100%" height="100%" />
  <text class="title" x="48" y="54">Icon Style Directions</text>
  <text class="subtitle" x="48" y="82">얇은 라인 아이콘이 밋밋해 보이는 문제를 기준으로, 더 눈에 들어오는 시각 방향을 비교합니다.</text>
  ${body}
</svg>`;
}

function sectionFrame(x, y, w, h, title, subtitle, tag) {
  return `
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="20" fill="#ffffff" stroke="#e2e8f0" />
    <text class="h2" x="${x + 24}" y="${y + 36}">${esc(title)}</text>
    <text class="desc" x="${x + 24}" y="${y + 58}">${esc(subtitle)}</text>
    ${tag ? `<rect x="${x + w - 116}" y="${y + 22}" width="86" height="28" rx="14" fill="#dcfce7" /><text x="${x + w - 73}" y="${y + 41}" text-anchor="middle" font-family="Malgun Gothic, Segoe UI, Arial" font-size="12" font-weight="800" fill="#15803d">${esc(tag)}</text>` : ""}
  `;
}

function lineCard(item, x, y) {
  const color = colors[item.tone];
  return `
    <g>
      <rect x="${x}" y="${y}" width="178" height="86" rx="16" fill="#ffffff" stroke="#e5e7eb" />
      <rect x="${x + 16}" y="${y + 14}" width="40" height="40" rx="12" fill="${color}" opacity="0.12" />
      ${lucideIcon(item.icon, x + 24, y + 22, 24, color, 2)}
      <text class="label" x="${x + 68}" y="${y + 37}">${esc(item.label)}</text>
      <text class="tiny" x="${x + 68}" y="${y + 58}">${esc(item.icon)}</text>
    </g>`;
}

function solidCard(item, x, y) {
  const color = colors[item.tone];
  return `
    <g>
      <rect x="${x}" y="${y}" width="178" height="86" rx="16" fill="#ffffff" stroke="#dbe4ee" />
      <rect x="${x + 16}" y="${y + 13}" width="46" height="46" rx="15" fill="${color}" />
      ${lucideIcon(item.icon, x + 27, y + 24, 24, "#ffffff", 2.35)}
      <text class="label" x="${x + 76}" y="${y + 36}">${esc(item.label)}</text>
      <rect x="${x + 76}" y="${y + 49}" width="58" height="5" rx="2.5" fill="${color}" opacity="0.32" />
    </g>`;
}

function emojiCard(item, x, y) {
  const color = colors[item.tone];
  return `
    <g>
      <rect x="${x}" y="${y}" width="178" height="86" rx="16" fill="#ffffff" stroke="#dbe4ee" />
      <rect x="${x + 16}" y="${y + 13}" width="46" height="46" rx="23" fill="${color}" opacity="0.12" />
      <text class="emoji" x="${x + 39}" y="${y + 46}" text-anchor="middle" font-size="25">${esc(item.emoji)}</text>
      <text class="label" x="${x + 76}" y="${y + 36}">${esc(item.label)}</text>
      <text class="small" x="${x + 76}" y="${y + 58}">emoji normalized</text>
    </g>`;
}

function mapMarker(item, x, y) {
  const color = colors[item.tone];
  return `
    <g>
      <path d="M${x + 28} ${y}c-15.5 0-28 12.5-28 28 0 21 28 48 28 48s28-27 28-48c0-15.5-12.5-28-28-28Z" fill="${color}" />
      <circle cx="${x + 28}" cy="${y + 28}" r="18" fill="#ffffff" opacity="0.94" />
      ${lucideIcon(item.icon, x + 18, y + 18, 20, color, 2.4)}
      <text class="small" x="${x + 28}" y="${y + 96}" text-anchor="middle">${esc(item.label)}</text>
    </g>`;
}

function chipLine(chip, x, y, mode) {
  const color = colors[chip.tone];
  const width = Math.max(118, 74 + Array.from(chip.label).length * 15);
  if (mode === "solid") {
    return `
      <g>
        <rect x="${x}" y="${y}" width="${width}" height="40" rx="20" fill="${color}" />
        ${lucideIcon(chip.icon, x + 13, y + 10, 20, "#ffffff", 2.35)}
        <text x="${x + 43}" y="${y + 26}" font-family="Malgun Gothic, Segoe UI, Arial" font-size="14" font-weight="800" fill="#ffffff">${esc(chip.label)}</text>
      </g>`;
  }
  if (mode === "emoji") {
    return `
      <g>
        <rect x="${x}" y="${y}" width="${width}" height="40" rx="20" fill="#ffffff" stroke="${color}" stroke-opacity="0.34" />
        <circle cx="${x + 22}" cy="${y + 20}" r="14" fill="${color}" opacity="0.12" />
        <text class="emoji" x="${x + 22}" y="${y + 26}" text-anchor="middle" font-size="17">${esc(chip.emoji)}</text>
        <text class="label" x="${x + 44}" y="${y + 26}" font-size="14">${esc(chip.label)}</text>
      </g>`;
  }
  return `
    <g>
      <rect x="${x}" y="${y}" width="${width}" height="40" rx="20" fill="#ffffff" stroke="${color}" stroke-opacity="0.24" />
      <circle cx="${x + 22}" cy="${y + 20}" r="14" fill="${color}" opacity="0.11" />
      ${lucideIcon(chip.icon, x + 14, y + 12, 16, color, 2.1)}
      <text class="label" x="${x + 44}" y="${y + 26}" font-size="14">${esc(chip.label)}</text>
    </g>`;
}

function brandChip(brand, x, y, compact = false) {
  const ink = brand.ink || "#ffffff";
  const w = compact ? 132 : 166;
  return `
    <g>
      <rect x="${x}" y="${y}" width="${w}" height="44" rx="22" fill="#ffffff" stroke="#dbe4ee" />
      <rect x="${x + 6}" y="${y + 6}" width="${compact ? 46 : 54}" height="32" rx="16" fill="${brand.color}" />
      <text x="${x + (compact ? 29 : 33)}" y="${y + 27}" text-anchor="middle" font-family="Malgun Gothic, Segoe UI, Arial" font-size="${brand.short.length > 3 ? 10 : 13}" font-weight="900" fill="${ink}">${esc(brand.short)}</text>
      <text class="label" x="${x + (compact ? 60 : 72)}" y="${y + 28}" font-size="14">${esc(brand.label)}</text>
    </g>`;
}

let body = "";

body += sectionFrame(
  48,
  112,
  1094,
  254,
  "A. Clean Line",
  "현재 2단계 미리보기와 가까운 방향입니다. 정돈감은 좋지만, 화면에서 힘이 약하고 기존 이모지보다 덜 즐거워 보입니다.",
  "보류",
);
samples.slice(0, 6).forEach((item, index) => {
  body += lineCard(item, 74 + index * 176, 202);
});

body += sectionFrame(
  48,
  392,
  1094,
  290,
  "B. Bold App Badge",
  "추천 1순위입니다. Lucide는 유지하되 솔리드 컬러 배지와 굵은 흰색 선으로 바꿔 기존보다 명확하고 앱답게 보이게 합니다.",
  "추천",
);
samples.slice(0, 6).forEach((item, index) => {
  body += solidCard(item, 74 + index * 176, 482);
});
chips.forEach((chip, index) => {
  body += chipLine(chip, 78 + index * 178, 596, "solid");
});

body += sectionFrame(
  48,
  708,
  1094,
  300,
  "C. Emoji Hybrid",
  "기존 감성은 살리고, 배지/크기/톤만 통일합니다. 친근함은 가장 좋지만 OS별 이모지 차이가 생길 수 있습니다.",
  "대안",
);
samples.slice(0, 6).forEach((item, index) => {
  body += emojiCard(item, 74 + index * 176, 798);
});
chips.forEach((chip, index) => {
  body += chipLine(chip, 78 + index * 178, 914, "emoji");
});

body += sectionFrame(
  48,
  1034,
  1094,
  312,
  "D. Map / Brand Forward",
  "Result 지도와 브랜드칩은 별도 규칙을 쓰는 편이 낫습니다. 카테고리 마커는 굵게, 브랜드칩은 로고/워드마크 우선으로 갑니다.",
  "혼합 추천",
);
samples.slice(0, 5).forEach((item, index) => {
  body += mapMarker(item, 86 + index * 120, 1124);
});
brands.forEach((brand, index) => {
  body += brandChip(brand, 690 + (index % 2) * 190, 1118 + Math.floor(index / 2) * 62, true);
});

body += `
  <rect x="48" y="1374" width="1094" height="118" rx="20" fill="#0f172a" />
  <text x="78" y="1412" font-family="Malgun Gothic, Segoe UI, Arial" font-size="20" font-weight="900" fill="#ffffff">제안 결론</text>
  <text x="78" y="1444" font-family="Malgun Gothic, Segoe UI, Arial" font-size="15" fill="#cbd5e1">Explore/Result 일반 아이콘은 B. Bold App Badge, 서브타입칩은 B의 작은 칩 버전, 브랜드 서브타입은 D의 로고 우선형을 추천합니다.</text>
  <text x="78" y="1472" font-family="Malgun Gothic, Segoe UI, Arial" font-size="15" fill="#cbd5e1">즉, Lucide 이름 검증은 유지하되 실제 표현은 얇은 라인이 아니라 굵은 컬러 배지로 가는 편이 기존보다 확실히 낫습니다.</text>
`;

fs.mkdirSync(outDir, { recursive: true });
const filePath = path.join(outDir, "04-style-directions.svg");
fs.writeFileSync(filePath, shell(1190, 1532, body), "utf8");
console.log(filePath);
