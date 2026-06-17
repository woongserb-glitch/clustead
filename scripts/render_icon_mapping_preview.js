const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const proposalPath = path.join(root, "docs", "icon_mapping_proposal.json");
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
  throw new Error("Lucide package was not found. Set LUCIDE_CJS_PATH to lucide/dist/cjs/lucide.js.");
}

const lucide = loadLucide();
const proposal = JSON.parse(fs.readFileSync(proposalPath, "utf8"));

const toneColors = {
  blue: "#2563eb",
  sky: "#0284c7",
  indigo: "#4f46e5",
  emerald: "#059669",
  green: "#16a34a",
  rose: "#e11d48",
  red: "#dc2626",
  violet: "#7c3aed",
  amber: "#d97706",
  teal: "#0d9488",
  orange: "#ea580c",
  yellow: "#ca8a04",
  purple: "#9333ea",
  brown: "#92400e",
  slate: "#475569",
  cyan: "#0891b2",
  pink: "#db2777",
};

const brandColors = {
  스타벅스: "#00704a",
  투썸플레이스: "#d31145",
  메가MGC: "#f7c600",
  컴포즈커피: "#f3c300",
  이디야: "#243b86",
  빽다방: "#ffe100",
  할리스: "#b5121b",
  커피빈: "#3a1f5d",
  폴바셋: "#111827",
  엔제리너스: "#c7152b",
  CU: "#642f8f",
  GS25: "#0072ce",
  세븐일레븐: "#008061",
  이마트24: "#ffd200",
  이마트: "#f4c400",
  홈플러스: "#e31b23",
  롯데마트: "#d71920",
  코스트코: "#005daa",
  트레이더스: "#f6c800",
  이마트에브리데이: "#f4c400",
  홈플러스익스프레스: "#e31b23",
  롯데슈퍼프레시: "#d71920",
  노브랜드: "#f4c400",
  GS더프레시: "#00a84f",
  하나로마트: "#009a44",
  W스토어: "#7c3aed",
  약국: "#16a34a",
};

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

function lucideIcon(iconName, x, y, size, color = "#334155") {
  const key = pascalIconName(iconName);
  const iconNode = lucide.icons?.[key] || lucide[key];
  if (!iconNode) {
    return `
      <g transform="translate(${x} ${y})">
        <circle cx="${size / 2}" cy="${size / 2}" r="${size / 2 - 2}" fill="#fee2e2" stroke="#ef4444" stroke-width="1.5" />
        <text x="${size / 2}" y="${size / 2 + 5}" text-anchor="middle" font-size="16" font-weight="700" fill="#dc2626">?</text>
      </g>`;
  }

  const scale = size / 24;
  const nodes = iconNode
    .map(([tag, attrs]) => `<${tag}${attrsToString(attrs)} />`)
    .join("");

  return `
    <g transform="translate(${x} ${y}) scale(${scale})" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      ${nodes}
    </g>`;
}

function svgShell(width, height, title, body) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <style>
    .bg { fill: #f8fafc; }
    .title { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 30px; font-weight: 800; fill: #0f172a; }
    .subtitle { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 14px; fill: #64748b; }
    .section { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 19px; font-weight: 800; fill: #111827; }
    .label { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 16px; font-weight: 800; fill: #111827; }
    .meta { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 12px; fill: #64748b; }
    .tiny { font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; font-size: 10px; fill: #64748b; }
    .emoji { font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif; font-size: 23px; }
    .mono { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; fill: #64748b; }
  </style>
  <rect class="bg" width="100%" height="100%" />
  <text class="title" x="44" y="52">${esc(title)}</text>
  <text class="subtitle" x="44" y="78">현재 이모지/표기와 추천 Lucide 또는 브랜드 로고 방향을 한눈에 보는 확정 전 미리보기입니다.</text>
  ${body}
</svg>`;
}

function currentText(item) {
  const icons = item.currentIcons || [item.currentIcon].filter(Boolean);
  return icons.length ? icons.join(" ") : "없음";
}

function drawRecommendation(rec, x, y, size, tone) {
  if (!rec) return "";
  const color = toneColors[rec.tone || tone] || "#334155";
  if (rec.type === "use_category_mapping") {
    return `<text class="meta" x="${x}" y="${y + 20}">category map</text>`;
  }
  if (rec.type === "badge" && rec.style === "subway-line-color-dot") {
    return `
      <circle cx="${x + 9}" cy="${y + 12}" r="6" fill="#2563eb" />
      <circle cx="${x + 24}" cy="${y + 12}" r="6" fill="#16a34a" />
      <circle cx="${x + 39}" cy="${y + 12}" r="6" fill="#f97316" />`;
  }
  if (rec.type === "badge") {
    const label = rec.label || "B";
    return `
      <rect x="${x}" y="${y}" width="${size}" height="${size}" rx="9" fill="${color}" opacity="0.14" />
      ${rec.icon ? lucideIcon(rec.icon, x + 7, y + 7, size - 14, color) : ""}
      <text x="${x + size - 7}" y="${y + size - 7}" text-anchor="end" font-size="10" font-weight="800" fill="${color}">${esc(label)}</text>`;
  }
  return lucideIcon(rec.icon || rec.fallbackIcon, x, y, size, color);
}

function card(item, x, y, w, h, kind) {
  const rec = item.recommended || {};
  const tone = rec.tone || "slate";
  const color = toneColors[tone] || "#334155";
  return `
    <g>
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="#ffffff" stroke="#e2e8f0" />
      <text class="meta" x="${x + 18}" y="${y + 23}">${esc(kind)} · ${esc(item.key || "")}</text>
      <text class="label" x="${x + 18}" y="${y + 49}">${esc(item.label || item.name || "")}</text>
      <text class="tiny" x="${x + 18}" y="${y + 69}">현재</text>
      <text class="emoji" x="${x + 58}" y="${y + 72}">${esc(currentText(item))}</text>
      <path d="M${x + w - 150} ${y + 46}h42" stroke="#cbd5e1" stroke-width="1.5" />
      <path d="M${x + w - 112} ${y + 40}l8 6-8 6" fill="none" stroke="#cbd5e1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      <rect x="${x + w - 74}" y="${y + 18}" width="50" height="50" rx="14" fill="${color}" opacity="0.11" />
      ${drawRecommendation(rec, x + w - 61, y + 31, 24, tone)}
      <text class="mono" x="${x + w - 99}" y="${y + 78}" text-anchor="middle">${esc(rec.icon || rec.fallbackIcon || rec.type || "")}</text>
    </g>`;
}

function renderOverviewPage() {
  const width = 1160;
  const margin = 44;
  const cardW = 522;
  const cardH = 88;
  const gapX = 28;
  const gapY = 14;
  const items = [
    ...proposal.domains.map((item) => ({ ...item, kind: "도메인" })),
    ...proposal.categories.map((item) => ({ ...item, kind: "카테고리" })),
  ];
  const rows = Math.ceil(items.length / 2);
  const height = 120 + rows * (cardH + gapY) + 40;
  let body = `
    <text class="section" x="${margin}" y="112">도메인 / 카테고리 아이콘</text>
    <text class="meta" x="${margin + 245}" y="112">총 ${items.length}개 · 현재 이모지에서 Lucide 라인 아이콘으로 통일</text>`;

  items.forEach((item, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = margin + col * (cardW + gapX);
    const y = 130 + row * (cardH + gapY);
    body += card(item, x, y, cardW, cardH, item.kind);
  });

  return svgShell(width, height, "Explore / Result Icon Mapping Preview", body);
}

function subtypeChip(label, currentIcon, rec, x, y, tone) {
  const color = toneColors[rec?.tone || tone] || "#334155";
  const labelLength = Array.from(label).length;
  const w = Math.max(154, Math.min(245, 78 + labelLength * 16));
  const h = 42;
  const old = currentIcon ? `<text class="emoji" x="${x + w - 34}" y="${y + 29}" opacity="0.55">${esc(currentIcon)}</text>` : "";
  return {
    width: w,
    svg: `
      <g>
        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="21" fill="#ffffff" stroke="${color}" stroke-opacity="0.26" />
        <rect x="${x + 8}" y="${y + 7}" width="28" height="28" rx="14" fill="${color}" opacity="0.12" />
        ${drawRecommendation(rec, x + 14, y + 13, 16, tone)}
        <text class="label" x="${x + 46}" y="${y + 27}" font-size="14">${esc(label)}</text>
        ${old}
      </g>`,
  };
}

function renderSubtypePage() {
  const width = 1220;
  const margin = 44;
  const contentW = width - margin * 2;
  const categoryByKey = new Map(proposal.categories.map((item) => [item.key, item]));
  let y = 122;
  let body = `
    <text class="section" x="${margin}" y="112">한글 서브타입칩 추천 아이콘</text>
    <text class="meta" x="${margin + 265}" y="112">칩 내부 16px 기준 · 기타/치과/한강공원은 검증 후 대체 적용</text>`;

  for (const [key, chips] of Object.entries(proposal.subtypes)) {
    const category = categoryByKey.get(key);
    const tone = category?.recommended?.tone || "slate";
    const color = toneColors[tone] || "#334155";
    const title = category?.label || key;
    const startY = y;
    let chipX = margin + 20;
    let chipY = y + 54;
    let sectionBody = `
      <text class="section" x="${margin + 20}" y="${y + 32}">${esc(title)}</text>
      <text class="meta" x="${margin + 135}" y="${y + 32}">${esc(key)}</text>`;

    for (const chip of chips) {
      const rendered = subtypeChip(chip.name, chip.currentIcon, chip.recommended, chipX, chipY, tone);
      if (chipX + rendered.width > margin + contentW - 20) {
        chipX = margin + 20;
        chipY += 54;
      }
      const rerendered = subtypeChip(chip.name, chip.currentIcon, chip.recommended, chipX, chipY, tone);
      sectionBody += rerendered.svg;
      chipX += rerendered.width + 10;
    }

    const sectionH = chipY - startY + 92;
    body += `
      <rect x="${margin}" y="${startY}" width="${contentW}" height="${sectionH}" rx="18" fill="#ffffff" stroke="#e2e8f0" />
      <rect x="${margin}" y="${startY}" width="7" height="${sectionH}" rx="3.5" fill="${color}" opacity="0.65" />
      ${sectionBody}`;
    y += sectionH + 18;
  }

  return svgShell(width, y + 38, "Subtype Chip Icon Preview", body);
}

function brandInitial(display) {
  const normalized = String(display || "").replace(/[^0-9A-Za-z가-힣]/g, "");
  return Array.from(normalized).slice(0, 3).join("");
}

function brandCard(item, group, x, y, w, h) {
  const color = brandColors[item.name] || brandColors[item.currentDisplay] || "#334155";
  const display = item.currentDisplay || item.name;
  const logoFile = item.logoFile || "generic lucide";
  const source = item.sourcePriority ? item.sourcePriority[0] : "lucide";
  const isGeneric = !item.logoFile && item.recommended?.icon;
  return `
    <g>
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="#ffffff" stroke="#e2e8f0" />
      <rect x="${x + 18}" y="${y + 18}" width="54" height="54" rx="16" fill="${color}" opacity="${item.name === "빽다방" || item.name === "메가MGC" || item.name === "트레이더스" || item.name === "이마트24" || item.name === "노브랜드" ? 0.72 : 0.92}" />
      ${
        isGeneric
          ? lucideIcon(item.recommended.icon, x + 33, y + 33, 24, "#ffffff")
          : `<text x="${x + 45}" y="${y + 52}" text-anchor="middle" font-size="14" font-weight="900" fill="#ffffff" font-family="Malgun Gothic, Segoe UI, Arial">${esc(brandInitial(display))}</text>`
      }
      <text class="label" x="${x + 86}" y="${y + 36}">${esc(display)}</text>
      <text class="meta" x="${x + 86}" y="${y + 58}">${esc(group)} · ${esc(source)}</text>
      <text class="mono" x="${x + 18}" y="${y + h - 16}">${esc(logoFile)}</text>
    </g>`;
}

function renderBrandPage() {
  const width = 1220;
  const margin = 44;
  const cardW = 354;
  const cardH = 112;
  const gapX = 20;
  const gapY = 16;
  let y = 122;
  let body = `
    <text class="section" x="${margin}" y="112">브랜드 서브타입칩 로고 대상</text>
    <text class="meta" x="${margin + 285}" y="112">실제 로고 파일 확보 전: 브랜드 컬러 플레이스홀더와 저장 경로 확인용</text>`;

  for (const [group, items] of Object.entries(proposal.brandSubtypes)) {
    body += `<text class="section" x="${margin}" y="${y + 22}">${esc(group)}</text>`;
    y += 42;
    items.forEach((item, index) => {
      const col = index % 3;
      const row = Math.floor(index / 3);
      const x = margin + col * (cardW + gapX);
      const cardY = y + row * (cardH + gapY);
      body += brandCard(item, group, x, cardY, cardW, cardH);
    });
    y += Math.ceil(items.length / 3) * (cardH + gapY) + 26;
  }

  return svgShell(width, y + 30, "Brand Chip Logo Preview", body);
}

function gallery(paths) {
  const images = paths
    .map((file) => {
      const name = path.basename(file);
      return `<section><h2>${esc(name)}</h2><img src="${esc(name)}" alt="${esc(name)}" /></section>`;
    })
    .join("\n");

  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>Icon Mapping Preview</title>
  <style>
    body { margin: 0; padding: 32px; background: #e5e7eb; font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif; color: #111827; }
    h1 { margin: 0 0 24px; font-size: 28px; }
    section { margin: 0 0 32px; }
    h2 { margin: 0 0 12px; font-size: 16px; color: #475569; }
    img { display: block; width: min(100%, 1220px); height: auto; border: 1px solid #cbd5e1; background: white; }
  </style>
</head>
<body>
  <h1>Icon Mapping Preview</h1>
  ${images}
</body>
</html>`;
}

fs.mkdirSync(outDir, { recursive: true });
const outputs = [
  ["01-domain-category-icons.svg", renderOverviewPage()],
  ["02-subtype-chip-icons.svg", renderSubtypePage()],
  ["03-brand-chip-logos.svg", renderBrandPage()],
];

const written = outputs.map(([name, content]) => {
  const filePath = path.join(outDir, name);
  fs.writeFileSync(filePath, content, "utf8");
  return filePath;
});

fs.writeFileSync(path.join(outDir, "index.html"), gallery(written), "utf8");

console.log(written.concat(path.join(outDir, "index.html")).join("\n"));
