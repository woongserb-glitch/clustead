/* ============================================================
   LiveFit Home — 네트워크 그래프 마인드맵
   center(아파트) → domain → category → brand/type
   조건을 순차 선택 → /explore 로 전달
   ============================================================ */
(function () {
    "use strict";

    var CONFIG;
    try {
        CONFIG = JSON.parse(document.getElementById("home-config").textContent);
    } catch (e) {
        console.error("home-config 파싱 실패", e);
        return;
    }
    if (!window.d3 || !d3.forceSimulation) {
        console.error("d3 로드 실패 — 그래프를 표시할 수 없습니다.");
        return;
    }

    /* ---------- 브랜드 마크(스타일라이즈 SVG 배지) ----------
       실제 로고 색상을 반영한 배지. svg 필드가 있으면 그 마크를 사용하고,
       없으면 {bg,fg,short} 로 컬러+약자 배지를 렌더한다.
       공식 로고 SVG가 있으면 svg 문자열만 교체하면 된다. */
    // 브랜드 서브타입 칩 색상 — Result 페이지의 brand chip 토큰과 동일(연한 배경 + 브랜드 글꼴색)
    var BRAND = {
        "이마트": { bg: "#fff3e8", fg: "#e85d04" },
        "홈플러스": { bg: "#ffe8ef", fg: "#c1121f" },
        "롯데마트": { bg: "#ffe8e8", fg: "#b00020" },
        "이마트에브리데이": { bg: "#fff7ed", fg: "#b45309" },
        "홈플러스익스프레스": { bg: "#fdf2f8", fg: "#be185d" },
        "롯데슈퍼프레시": { bg: "#fff1f2", fg: "#be123c" },
        "노브랜드": { bg: "#f8fafc", fg: "#334155" },
        "GS더프레시": { bg: "#ecfeff", fg: "#0e7490" },
        "하나로마트": { bg: "#ecfdf5", fg: "#047857" },
        "코스트코": { bg: "#e8f0ff", fg: "#1f4e9e" },
        "트레이더스": { bg: "#fff4cc", fg: "#7a5c00" },
        "CU": { bg: "#efe8ff", fg: "#5b2ca0" },
        "GS25": { bg: "#e8f7ff", fg: "#0077a8" },
        "세븐일레븐": { bg: "#fff0e6", fg: "#d35400" },
        "이마트24": { bg: "#fff4cc", fg: "#6f5800" },
        "스타벅스": { bg: "#e7f6ef", fg: "#00704a" },
        "투썸플레이스": { bg: "#f8e8ea", fg: "#7b1e28" },
        "메가MGC": { bg: "#fff7cc", fg: "#8a6b00" },
        "컴포즈커피": { bg: "#fff1c9", fg: "#222222" },
        "이디야": { bg: "#e8f0ff", fg: "#244c9a" },
        "빽다방": { bg: "#e9f7ff", fg: "#0077b6" },
        "할리스": { bg: "#fdecec", fg: "#c0102e" },
        "커피빈": { bg: "#eaeef5", fg: "#15375c" },
        "폴바셋": { bg: "#f1ebe4", fg: "#5a3b25" },
        "엔제리너스": { bg: "#eef3e3", fg: "#586c1c" }
    };
    var NEUTRAL_CHIP = { bg: "#ffffff", fg: "#555c68", stroke: "#e1e5ec" };
    function domainIconOf(domainKey) {
        var d = (CONFIG.domains || []).filter(function (x) { return x.key === domainKey; })[0];
        return d ? d.icon : "";
    }

    /* ---------- 노드/링크 모델 빌드 ---------- */
    var nodes = [];
    var links = [];
    var nodeById = {};

    function addNode(n) {
        nodeById[n.id] = n;
        nodes.push(n);
        return n;
    }

    var center = addNode({
        id: "center", type: "center", label: "아파트", icon: "🏢",
        color: "#f5b301", r: 60, depth: 0
    });

    function addLeaf(parentId, depth, dom, catKey, sub) {
        var brand = BRAND[sub] || null;
        addNode({
            id: "l:" + catKey + ":" + sub, type: "leaf", leafKind: "priority",
            label: sub, color: dom.color, r: 23, depth: depth,
            domainKey: dom.key, categoryKey: catKey, subtype: sub,
            brand: brand, parentId: parentId
        });
        links.push({ source: parentId, target: "l:" + catKey + ":" + sub, depth: depth });
    }

    CONFIG.domains.forEach(function (dom) {
        var dId = "d:" + dom.key;
        var cats = dom.categories || [];
        // 도메인에 단일 priority 카테고리(라벨 중복: 의료/문화)면 도메인 자체를 카테고리로 평탄화 → 중복 노드 제거
        var merged = (cats.length === 1 && cats[0].kind === "priority");

        var domainNode = {
            id: dId, type: "domain", label: dom.label, icon: dom.icon,
            color: dom.color, r: 42, depth: 1, domainKey: dom.key, parentId: "center"
        };
        if (merged) {
            domainNode.merged = true;
            domainNode.kind = "priority";
            domainNode.categoryKey = cats[0].key;
            domainNode.cat = cats[0];
        }
        addNode(domainNode);
        links.push({ source: "center", target: dId, depth: 1 });

        if (merged) {
            // 리프를 도메인에 직접 붙임(depth 2)
            (cats[0].subtypes || []).forEach(function (sub) {
                addLeaf(dId, 2, dom, cats[0].key, sub);
            });
            return;
        }

        cats.forEach(function (cat) {
            var cId = "c:" + dom.key + ":" + cat.key;
            addNode({
                id: cId, type: "category", label: cat.label, icon: cat.icon,
                color: dom.color, r: 30, depth: 2,
                domainKey: dom.key, categoryKey: cat.key, kind: cat.kind, cat: cat,
                parentId: dId
            });
            links.push({ source: dId, target: cId, depth: 2 });

            if (cat.kind === "priority") {
                (cat.subtypes || []).forEach(function (sub) { addLeaf(cId, 3, dom, cat.key, sub); });
            }
        });
    });

    /* ---------- 펼침/선택 상태 ---------- */
    var expandedDomains = {};
    var expandedCats = {};
    function resetHomeExpansionState() {
        CONFIG.domains.forEach(function (d) { expandedDomains[d.key] = true; });
        expandedCats = {};
        nodes.forEach(function (n) {
            if (n.type === "domain" && n.merged) expandedCats["c:" + n.domainKey + ":" + n.categoryKey] = true;
        });
    }
    function expandAllNodes() {
        CONFIG.domains.forEach(function (d) { expandedDomains[d.key] = true; });
        nodes.forEach(function (n) {
            if ((n.type === "domain" && n.merged) || (n.type === "category" && n.kind === "priority")) {
                expandedCats["c:" + n.domainKey + ":" + n.categoryKey] = true;
            }
        });
    }
    function allNodesExpanded() {
        var expanded = true;
        CONFIG.domains.forEach(function (d) {
            if (!expandedDomains[d.key]) expanded = false;
        });
        nodes.forEach(function (n) {
            if ((n.type === "domain" && n.merged) || (n.type === "category" && n.kind === "priority")) {
                if (!expandedCats["c:" + n.domainKey + ":" + n.categoryKey]) expanded = false;
            }
        });
        return expanded;
    }
    // 첫 화면: 1차 클러스터 모두 오픈 — 평탄화 도메인(의료/문화)의 리프도 펼쳐둔다
    resetHomeExpansionState();

    // selections: 순서 보존 배열
    var selections = [];
    // presets
    var preset = { gu: "", dong: "", area: [], household: "", price_type: "trade", price: "" };

    function selIndex(id) {
        for (var i = 0; i < selections.length; i++) if (selections[i].selId === id) return i;
        return -1;
    }

    function isNodeSelected(n) {
        if (n.type === "leaf") return selIndex("p:" + n.categoryKey + ":" + n.subtype) >= 0;
        if (n.type === "category") {
            if (n.kind === "toggle") return selIndex("t:" + n.cat.param) >= 0;
            if (n.kind === "autocomplete") return selIndex("a:" + n.cat.param) >= 0;
        }
        return false;
    }

    /* ---------- 가시성 ---------- */
    function isVisible(n) {
        if (n.depth <= 1) return true;
        if (n.depth === 2) {
            // 평탄화 도메인의 리프(depth2 leaf) → 도메인 펼침(expandedCats) 시 표시
            if (n.type === "leaf") return !!expandedCats["c:" + n.domainKey + ":" + n.categoryKey];
            return !!expandedDomains[n.domainKey]; // 일반 카테고리
        }
        if (n.depth === 3) return !!expandedDomains[n.domainKey] && !!expandedCats["c:" + n.domainKey + ":" + n.categoryKey];
        return true;
    }

    /* ---------- SVG 셋업 ---------- */
    var stage = document.querySelector("[data-stage]");
    var svg = d3.select("[data-svg]");
    var root = svg.append("g").attr("class", "hg-root");
    var linkG = root.append("g").attr("class", "hg-links");
    var nodeG = root.append("g").attr("class", "hg-nodes");

    var W = stage.clientWidth, H = stage.clientHeight;
    var cx = W / 2, cy = H / 2;

    center.fx = cx; center.fy = cy;
    center.x = cx; center.y = cy;

    var zoom = d3.zoom()
        .scaleExtent([0.35, 2.6])
        .on("zoom", function (ev) { root.attr("transform", ev.transform); });
    svg.call(zoom).on("dblclick.zoom", null);

    // 깊이별 링 반경 — 레벨마다 고유 원에 배치해 가지 엉킴 방지
    var RING = { 1: 215, 2: 375, 3: 510 };
    function ringR(d) { return RING[d.depth] || 0; }

    /* ---------- 힘 시뮬레이션 ----------
       1·2차는 고유 링에 고정. 3차 리프는 링을 강제하지 않고(부모 주변 자유 분산)
       charge 반발 + collide 로 바깥으로 흩어지게 한다(유기적 움직임). */
    var sim = d3.forceSimulation()
        .force("link", d3.forceLink().id(function (d) { return d.id; })
            .distance(function (l) { return l.depth === 1 ? 205 : l.depth === 2 ? 160 : 108; })
            .strength(function (l) { return l.depth === 1 ? 0.45 : l.depth === 2 ? 0.4 : 0.55; }))
        .force("charge", d3.forceManyBody()
            .strength(function (d) { return d.depth === 1 ? -700 : d.depth === 2 ? -340 : -260; })
            .distanceMax(700))
        .force("collide", d3.forceCollide().radius(function (d) { return d.r + 10; }).iterations(4))
        .force("radial", d3.forceRadial(ringR, cx, cy)
            .strength(function (d) { return d.depth === 1 ? 0.6 : d.depth === 2 ? 0.55 : 0; }))
        .force("x", d3.forceX(cx).strength(0.006))
        .force("y", d3.forceY(cy).strength(0.006))
        .on("tick", ticked);

    var linkSel, nodeSel;

    function restart(alpha) {
        var vnodes = nodes.filter(isVisible);
        var visIds = {};
        vnodes.forEach(function (n) { visIds[n.id] = true; });

        // 새로 등장하는 노드(펼침)는 부모에서 바깥쪽(중심→부모 방향)으로 작은 부채꼴로 시딩
        // → 좌상단 쏠림/엉킴 없이 부모로부터 가지처럼 뻗어 나간다.
        var newByParent = {};
        vnodes.forEach(function (n) {
            if (n.x == null || isNaN(n.x)) (newByParent[n.parentId] = newByParent[n.parentId] || []).push(n);
        });
        Object.keys(newByParent).forEach(function (pid) {
            var p = nodeById[pid];
            var px = (p && p.x != null) ? p.x : cx;
            var py = (p && p.y != null) ? p.y : cy;
            var baseAng = Math.atan2(py - cy, px - cx);   // 중심 → 부모 바깥 방향
            if (px === cx && py === cy) baseAng = -Math.PI / 2;
            var group = newByParent[pid];
            var spread = Math.min(Math.PI * 0.7, 0.32 * group.length);
            group.forEach(function (n, i) {
                var a = baseAng + (group.length === 1 ? 0 : (i / (group.length - 1) - 0.5) * spread);
                n.x = px + Math.cos(a) * 46;
                n.y = py + Math.sin(a) * 46;
                n.vx = 0;
                n.vy = 0;
            });
        });
        var vlinks = links.filter(function (l) {
            var s = l.source.id || l.source, t = l.target.id || l.target;
            return visIds[s] && visIds[t];
        });

        // links
        linkSel = linkG.selectAll("path.hg-link").data(vlinks, function (l) {
            return (l.source.id || l.source) + "->" + (l.target.id || l.target);
        });
        linkSel.exit().remove();
        linkSel = linkSel.enter().append("path").attr("class", "hg-link").merge(linkSel);

        // nodes
        nodeSel = nodeG.selectAll("g.hg-node").data(vnodes, function (d) { return d.id; });
        nodeSel.exit().remove();
        var enter = nodeSel.enter().append("g")
            .attr("class", "hg-node")
            .call(d3.drag()
                .on("start", dragStart)
                .on("drag", dragging)
                .on("end", dragEnd))
            .on("click", onNodeClick)
            .on("mouseenter", onNodeEnter)
            .on("mouseleave", onNodeLeave);

        enter.each(function (d) { buildNodeVisual(d3.select(this), d); });
        nodeSel = enter.merge(nodeSel);
        nodeSel.attr("class", nodeClass);
        nodeSel.each(function (d) { refreshNodeState(d3.select(this), d); });

        sim.nodes(vnodes);
        sim.force("link").links(vlinks);
        sim.alpha(alpha || 0.6).restart();

        if (typeof pruneOrphanPanels === "function") pruneOrphanPanels();   // 사라진 노드의 패널 닫기
        if (typeof markSearchingNodes === "function") markSearchingNodes();  // 검색중 글로우 재적용
    }

    function nodeClass(d) {
        var c = "hg-node depth-" + d.depth;
        if (d.type === "center") c += " is-center";
        if (d.type === "domain") c += " is-domain";
        if (isNodeSelected(d)) c += " is-selected";
        var isPriorityParent = (d.type === "category" && d.kind === "priority") || (d.type === "domain" && d.merged);
        if (isPriorityParent && !expandedCats["c:" + d.domainKey + ":" + d.categoryKey]
            && (d.cat.subtypes || []).length) c += " is-collapsed-parent";
        return c;
    }

    // 알약형 서브타입 칩 (리프/카테고리 공용). tokens=[{t, fs}], size={h, fs, padX}.
    function renderChip(g, d, tokens, bg, fg, stroke, size) {
        size = size || {};
        var fs = size.fs || 11.5, h = size.h || 25, padX = size.padX || 12;
        var text = g.append("text").attr("class", "hg-leaf-text")
            .attr("text-anchor", "middle").attr("dy", "0.34em")
            .style("font-size", fs + "px").style("font-weight", "800")
            .style("fill", fg).style("pointer-events", "none");
        tokens.forEach(function (tk) {
            text.append("tspan").style("font-size", (tk.fs || fs) + "px").text(tk.t);
        });
        var bw;
        try { bw = text.node().getBBox().width; }
        catch (e) { bw = tokens.reduce(function (s, tk) { return s + tk.t.length * (tk.fs || fs) * 0.62; }, 0); }
        var w = Math.max(bw + padX * 2, h + 8);
        g.insert("rect", ".hg-leaf-text")
            .attr("class", "hg-leaf-chip")
            .attr("x", -w / 2).attr("y", -h / 2)
            .attr("width", w).attr("height", h)
            .attr("rx", h / 2).attr("ry", h / 2)
            .style("fill", bg).style("stroke", stroke).style("stroke-width", "1px");
        d._w = w; d._h = h; d.r = Math.max(w, h) / 2;
        d._chipBg = bg; d._chipFg = fg; d._chipStroke = stroke;
    }

    // 원 안 "아이콘+텍스트"를 정중앙에 세로 배치 — 실제 높이를 측정해 간격 확보 + 중앙정렬
    function centerStack(g, icon, iconSize, label, labelSize, labelColor) {
        var iconT = g.append("text").attr("class", "hg-node-icon")
            .attr("text-anchor", "middle").attr("dominant-baseline", "central").attr("y", 0)
            .style("font-size", iconSize + "px").style("pointer-events", "none").text(icon);
        var labelT = g.append("text").attr("class", "hg-center-label")
            .attr("text-anchor", "middle").attr("dominant-baseline", "central").attr("y", 0)
            .style("font-size", labelSize + "px").style("fill", labelColor).text(label);
        var ih, lh;
        try { ih = iconT.node().getBBox().height; } catch (e) { ih = iconSize; }
        try { lh = labelT.node().getBBox().height; } catch (e) { lh = labelSize; }
        var gap = 8;                        // 아이콘과 텍스트 사이 여백
        var total = ih + gap + lh;
        iconT.attr("y", -total / 2 + ih / 2);
        labelT.attr("y", total / 2 - lh / 2);
    }

    function buildNodeVisual(g, d) {
        if (d.type === "leaf") {
            g.style("color", d.color);
            var bc = d.brand || NEUTRAL_CHIP;
            var big = d.depth <= 2;          // 평탄화 도메인 직속 리프(depth2)는 2차급 → 크게 + 아이콘
            var sz = big ? { h: 30, fs: 13, padX: 13 } : { h: 25, fs: 11.5, padX: 12 };
            var tokens = (d.depth === 2)
                ? [{ t: domainIconOf(d.domainKey) + " ", fs: 16 }, { t: d.label }]  // 의료/문화 아이콘
                : [{ t: d.label }];
            renderChip(g, d, tokens, bc.bg, bc.fg, bc.stroke || bc.fg, sz);

        } else if (d.type === "category") {
            g.style("color", d.color);
            // 2차 = 아이콘+텍스트 서브타입 칩(중립, 크게). 고유 아이콘 없으면 도메인 아이콘.
            var icon = d.icon || domainIconOf(d.domainKey);
            renderChip(g, d, [{ t: icon + " ", fs: 16 }, { t: d.label }],
                NEUTRAL_CHIP.bg, NEUTRAL_CHIP.fg, NEUTRAL_CHIP.stroke, { h: 30, fs: 13, padX: 13 });

        } else if (d.type === "center") {
            // 중앙 아파트: 연한 골드 원 + 아이콘+텍스트 정중앙
            g.append("circle").attr("class", "hg-node-circle").attr("r", d.r)
                .style("fill", "#fdeecb").style("stroke", "#f0c24a").style("stroke-width", "2px").style("color", d.color);
            centerStack(g, "🏢", 34, d.label, 14, "#5a4500");

        } else {
            // 1차 도메인: 흰 원 + 컬러 링 + 아이콘(크게)+텍스트 정중앙
            g.append("circle").attr("class", "hg-node-circle").attr("r", d.r)
                .style("fill", "#ffffff").style("stroke", d.color).style("stroke-width", "3px").style("color", d.color);
            centerStack(g, d.icon, 30, d.label, 11.5, "#1f2937");
        }

        // 선택 체크 배지 (칩은 우상단, 원형 노드는 원 우상단)
        var isPill = (d._w != null);
        var bx = isPill ? (d._w / 2 - 2) : d.r * 0.72;
        var by = isPill ? (-d._h / 2) : -d.r * 0.72;
        g.append("circle").attr("class", "hg-node-badge").attr("r", 6)
            .attr("cx", bx).attr("cy", by).style("display", "none");
        g.append("text").attr("class", "hg-node-badge-tick")
            .attr("x", bx).attr("y", by).attr("dy", "0.32em")
            .attr("text-anchor", "middle").style("font-size", "8px").style("fill", "#fff")
            .style("font-weight", "900").style("pointer-events", "none")
            .style("display", "none").text("✓");
    }

    function refreshNodeState(g, d) {
        var on = isNodeSelected(d);
        g.select(".hg-node-badge").style("display", on ? null : "none");
        g.select(".hg-node-badge-tick").style("display", on ? null : "none");
        // 칩(리프/카테고리) 선택 상태 — 선택 시 강조(파랑), 해제 시 본래 색 복원
        if (d._w != null) {
            g.select(".hg-leaf-chip")
                .style("fill", on ? "#2563eb" : d._chipBg)
                .style("stroke", on ? "#2563eb" : d._chipStroke);
            g.select(".hg-leaf-text").style("fill", on ? "#ffffff" : d._chipFg);
        }
    }

    function ticked() {
        if (linkSel) linkSel.attr("d", function (l) {
            var s = l.source, t = l.target;
            var dx = t.x - s.x, dy = t.y - s.y;
            var dr = Math.sqrt(dx * dx + dy * dy) * 2.6;
            return "M" + s.x + "," + s.y + "A" + dr + "," + dr + " 0 0,1 " + t.x + "," + t.y;
        });
        if (nodeSel) nodeSel.attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });
    }

    /* ---------- 드래그 ---------- */
    function dragStart(ev, d) {
        if (!ev.active) sim.alphaTarget(0.2).restart();
        d.fx = d.x; d.fy = d.y;
        d._dragMoved = false;
    }
    function dragging(ev, d) {
        d.fx = ev.x; d.fy = ev.y;
        if (Math.abs(ev.dx) > 0.5 || Math.abs(ev.dy) > 0.5) d._dragMoved = true;
    }
    function dragEnd(ev, d) {
        if (!ev.active) sim.alphaTarget(0);
        if (d.type !== "center") { d.fx = null; d.fy = null; }
    }

    /* ---------- 노드 클릭 ---------- */
    function onNodeClick(ev, d) {
        if (d._dragMoved) { d._dragMoved = false; return; }
        ev.stopPropagation();

        if (d.type === "center") {
            stopCenterCascade();
            if (allNodesExpanded()) {
                resetHomeExpansionState();
                radialSeed();
                restart(0.7);
            } else {
                expandAllNodes();
                restart(0.6);
            }
            return;
        }
        if (d.type === "domain") {
            if (d.merged) {  // 평탄화 도메인(의료/문화) → 리프 펼침/접힘
                var mk = "c:" + d.domainKey + ":" + d.categoryKey;
                expandedCats[mk] = !expandedCats[mk];
            } else {
                expandedDomains[d.domainKey] = !expandedDomains[d.domainKey];
            }
            restart(0.5);
            return;
        }
        if (d.type === "category") {
            if (d.kind === "priority") {
                var k = "c:" + d.domainKey + ":" + d.categoryKey;
                expandedCats[k] = !expandedCats[k];
                restart(0.5);
            } else if (d.kind === "toggle") {
                toggleSelection({ selId: "t:" + d.cat.param, kind: "toggle", param: d.cat.param, label: d.label, sub: d.cat.hint || "" });
            } else if (d.kind === "autocomplete") {
                toggleSearchPanel(d);   // 같은 노드 재클릭 → 닫힘(토글)
            }
            return;
        }
        if (d.type === "leaf" && d.leafKind === "priority") {
            toggleSelection({
                selId: "p:" + d.categoryKey + ":" + d.subtype, kind: "priority",
                category: d.categoryKey, subtype: d.subtype,
                label: d.subtype, sub: catLabel(d.categoryKey)
            });
        }
    }

    function catLabel(catKey) {
        var found = "";
        CONFIG.domains.forEach(function (dom) {
            (dom.categories || []).forEach(function (c) { if (c.key === catKey) found = c.label; });
        });
        return found;
    }

    function toggleSelection(sel) {
        var i = selIndex(sel.selId);
        if (i >= 0) selections.splice(i, 1);
        else selections.push(sel);
        syncSelections();
    }

    function setParamSelection(param, value, label, sub) {
        var id = "a:" + param;
        var i = selIndex(id);
        var sel = { selId: id, kind: "param", param: param, value: value, label: label, sub: sub };
        if (i >= 0) selections[i] = sel;
        else selections.push(sel);
        syncSelections();
    }

    function removeSelection(selId) {
        var i = selIndex(selId);
        if (i >= 0) { selections.splice(i, 1); syncSelections(); }
    }

    function syncSelections() {
        if (nodeSel) nodeSel.attr("class", nodeClass).each(function (d) { refreshNodeState(d3.select(this), d); });
        renderTray();
    }

    /* ---------- 호버 툴팁(브랜드명) ---------- */
    var tooltip = document.querySelector("[data-tooltip]");
    function ancestorIdsOf(d) {
        var ids = {};
        var pid = d.parentId;
        while (pid) {
            ids[pid] = true;
            var parent = nodeById[pid];
            pid = parent && parent.parentId;
        }
        return ids;
    }
    function endpointIdOf(linkEnd) {
        return linkEnd && linkEnd.id ? linkEnd.id : linkEnd;
    }
    var centerCascadeTimers = [];
    function stopCenterCascade() {
        centerCascadeTimers.forEach(function (timer) { clearTimeout(timer); });
        centerCascadeTimers = [];
        if (nodeSel) nodeSel.classed("is-cascade-active", false);
    }
    function maxVisibleDepth() {
        var maxDepth = 0;
        if (nodeSel) nodeSel.each(function (n) {
            if (n.depth > maxDepth) maxDepth = n.depth;
        });
        return maxDepth;
    }
    function linkDepthOf(l) {
        var source = nodeById[endpointIdOf(l.source)];
        var target = nodeById[endpointIdOf(l.target)];
        if (!source || !target) return Infinity;
        return Math.max(source.depth, target.depth);
    }
    function isDescendantOf(node, rootId) {
        var pid = node.parentId;
        while (pid) {
            if (pid === rootId) return true;
            var parent = nodeById[pid];
            pid = parent && parent.parentId;
        }
        return false;
    }
    function maxVisibleDescendantDepth(root) {
        var maxDepth = root.depth;
        if (nodeSel) nodeSel.each(function (n) {
            if (isDescendantOf(n, root.id) && n.depth > maxDepth) maxDepth = n.depth;
        });
        return maxDepth;
    }
    function setDomainCascadeStep(domain, maxDepth) {
        var activeIds = {};
        if (domain.parentId) activeIds[domain.parentId] = true;
        activeIds[domain.id] = true;
        if (nodeSel) nodeSel.classed("is-cascade-active", function (n) {
            var active = n.id === domain.id || n.id === domain.parentId
                || (isDescendantOf(n, domain.id) && n.depth <= maxDepth);
            if (active) activeIds[n.id] = true;
            return active;
        });
        if (linkSel) linkSel.classed("is-active", function (l) {
            return !!(activeIds[endpointIdOf(l.source)] && activeIds[endpointIdOf(l.target)]);
        });
    }
    function startDomainCascade(domain) {
        stopCenterCascade();
        if (nodeSel) nodeSel.classed("is-hover-ancestor", false);
        if (linkSel) linkSel.classed("is-active", false);
        setDomainCascadeStep(domain, domain.depth);

        var maxDepth = maxVisibleDescendantDepth(domain);
        for (var depth = domain.depth + 1; depth <= maxDepth; depth += 1) {
            (function (step) {
                centerCascadeTimers.push(setTimeout(function () {
                    setDomainCascadeStep(domain, step);
                }, (step - domain.depth) * 95));
            })(depth);
        }
    }
    function startCenterCascade() {
        stopCenterCascade();
        if (nodeSel) nodeSel.classed("is-hover-ancestor", false);
        if (nodeSel) nodeSel.classed("is-cascade-active", function (n) { return n.depth === 0; });
        if (linkSel) linkSel.classed("is-active", false);

        var maxDepth = maxVisibleDepth();
        for (var depth = 1; depth <= maxDepth; depth += 1) {
            (function (step) {
                centerCascadeTimers.push(setTimeout(function () {
                    if (nodeSel) nodeSel.classed("is-cascade-active", function (n) { return n.depth <= step; });
                    if (linkSel) linkSel.classed("is-active", function (l) { return linkDepthOf(l) <= step; });
                }, step * 95));
            })(depth);
        }
    }
    function onNodeEnter(ev, d) {
        // 링크 강조 (리프 라벨은 칩에 그대로 보이므로 툴팁 불필요)
        stopCenterCascade();
        if (nodeSel) nodeSel.classed("is-hover-ancestor", false);
        if (d.type === "center") {
            startCenterCascade();
            return;
        }
        if (d.type === "domain") {
            startDomainCascade(d);
            return;
        }
        var ancestorIds = ancestorIdsOf(d);
        var pathIds = {};
        pathIds[d.id] = true;
        Object.keys(ancestorIds).forEach(function (id) { pathIds[id] = true; });
        if (linkSel) linkSel.classed("is-active", function (l) {
            var sourceId = endpointIdOf(l.source);
            var targetId = endpointIdOf(l.target);
            return !!(pathIds[sourceId] && pathIds[targetId]);
        });
        if (nodeSel) nodeSel.classed("is-hover-ancestor", function (n) { return !!ancestorIds[n.id]; });
    }
    function onNodeLeave() {
        stopCenterCascade();
        if (linkSel) linkSel.classed("is-active", false);
        if (nodeSel) nodeSel.classed("is-hover-ancestor", false);
        tooltip.hidden = true;
    }
    function positionTooltip(d) {
        var t = d3.zoomTransform(svg.node());
        var sx = t.applyX(d.x), sy = t.applyY(d.y);
        var rect = stage.getBoundingClientRect();
        tooltip.style.left = sx + "px";
        tooltip.style.top = (sy - d.r * t.k) + "px";
    }

    /* ---------- 노드 검색 패널 (여러 개 동시 · 좌측 스택 · 닫기 전까지 유지) ---------- */
    var searchStack = document.querySelector("[data-search-stack]");
    var openPanels = {};   // categoryKey -> { el, node, cat, input, menu, selectedEl, token, debounce }

    function toggleSearchPanel(d) {
        if (openPanels[d.categoryKey]) closeSearchPanel(d.categoryKey);
        else openSearchPanel(d);
    }

    function openSearchPanel(d) {
        var cat = d.cat;
        var key = d.categoryKey;
        var panel = document.createElement("div");
        panel.className = "hg-search-panel";
        panel.innerHTML =
            '<div class="hg-search-head"><span class="hg-search-dot"></span>' +
            '<b></b><button type="button" class="hg-search-close" aria-label="닫기">✕</button></div>' +
            '<div class="hg-search-field"><input type="text" autocomplete="off"></div>' +
            '<div class="hg-search-selected" hidden></div>' +
            '<div class="hg-search-menu"></div>';
        panel.querySelector("b").textContent = d.label;
        var input = panel.querySelector("input");
        input.placeholder = cat.placeholder || "검색";
        searchStack.appendChild(panel);

        var rec = {
            el: panel, node: d, cat: cat, input: input,
            menu: panel.querySelector(".hg-search-menu"),
            selectedEl: panel.querySelector(".hg-search-selected"),
            token: 0, debounce: null
        };
        openPanels[key] = rec;

        // 노드 고정(드리프트 방지) + 활성 글로우
        d.fx = d.x; d.fy = d.y;
        markSearchingNodes();

        // 이미 선택된 값이 있으면 반영
        var cur = currentParamSelection(cat.param);
        if (cur) { input.value = cur.value; showPanelSelected(rec, cur.label); }

        panel.querySelector(".hg-search-close").addEventListener("click", function () { closeSearchPanel(key); });
        input.addEventListener("input", function () {
            clearTimeout(rec.debounce);
            var q = input.value;
            rec.debounce = setTimeout(function () { fetchPanel(rec, q); }, 180);
        });
        input.addEventListener("keydown", function (e) { if (e.key === "Escape") closeSearchPanel(key); });

        fetchPanel(rec, input.value || "");
        input.focus();
    }

    function closeSearchPanel(key) {
        var rec = openPanels[key];
        if (!rec) return;
        rec.el.remove();
        if (rec.node && rec.node.type !== "center") { rec.node.fx = null; rec.node.fy = null; }
        delete openPanels[key];
        markSearchingNodes();
    }

    function currentParamSelection(param) {
        for (var i = 0; i < selections.length; i++) {
            if (selections[i].kind === "param" && selections[i].param === param) return selections[i];
        }
        return null;
    }

    // 검색 패널이 열린 노드(들)에 글로우 — 동시에 여러 개 가능
    function markSearchingNodes() {
        if (nodeSel) nodeSel.classed("is-searching", function (n) {
            return n.categoryKey && openPanels[n.categoryKey] && (n.type === "category" || n.merged);
        });
    }

    function fetchPanel(rec, q) {
        var token = ++rec.token;
        var url = rec.cat.endpoint + "?q=" + encodeURIComponent(q || "");
        if (rec.cat.filter_param) {   // 예: 역 검색을 선택한 노선으로 제한
            var fp = currentParamSelection(rec.cat.filter_param);
            if (fp) url += "&" + rec.cat.filter_param + "=" + encodeURIComponent(fp.value);
        }
        fetch(url).then(function (r) { return r.json(); }).then(function (data) {
            if (token !== rec.token) return;  // race 방지
            renderPanelMenu(rec, data.items || []);
        }).catch(function () { if (token === rec.token) renderPanelMenu(rec, []); });
    }

    function renderPanelMenu(rec, items) {
        rec.menu.innerHTML = "";
        if (!items.length) {
            rec.menu.innerHTML = '<div class="hg-search-empty">검색 결과가 없습니다</div>';
            return;
        }
        var curVal = (currentParamSelection(rec.cat.param) || {}).value;
        items.forEach(function (it) {
            var b = document.createElement("button");
            b.type = "button";
            b.innerHTML = escapeHtml(it.label || it.value) +
                (it.meta ? '<span class="hg-menu-meta">' + escapeHtml(it.meta) + "</span>" : "");
            if (curVal === it.value) b.classList.add("is-active");
            b.addEventListener("click", function () {
                setParamSelection(rec.cat.param, it.value, (it.label || it.value), rec.cat.label);
                rec.input.value = it.label || it.value;
                showPanelSelected(rec, it.label || it.value);
                rec.menu.querySelectorAll("button").forEach(function (x) { x.classList.remove("is-active"); });
                b.classList.add("is-active");
                // 닫지 않고 유지(사용자 요청). 노선 선택 시 열려있는 역 패널은 결과 갱신.
                refreshDependentPanels(rec.cat.param);
            });
            rec.menu.appendChild(b);
        });
    }

    function showPanelSelected(rec, label) {
        rec.selectedEl.hidden = false;
        rec.selectedEl.innerHTML = '선택됨: <b>' + escapeHtml(label) + "</b>";
    }

    // filter_param 이 바뀌면(예: 노선 변경) 그것에 의존하는 열린 패널(역) 재조회
    function refreshDependentPanels(changedParam) {
        Object.keys(openPanels).forEach(function (k) {
            var rec = openPanels[k];
            if (rec.cat.filter_param === changedParam) fetchPanel(rec, rec.input.value || "");
        });
    }

    // 부모가 접혀 노드가 사라지면 해당 패널도 닫기
    function pruneOrphanPanels() {
        Object.keys(openPanels).forEach(function (k) {
            if (!isVisible(openPanels[k].node)) closeSearchPanel(k);
        });
    }

    /* ---------- 선택 트레이 ---------- */
    var tray = document.querySelector("[data-tray]");
    var trayList = document.querySelector("[data-tray-list]");
    var trayCount = document.querySelector("[data-tray-count]");
    var trayFab = document.querySelector("[data-tray-fab]");
    var fabCount = document.querySelector("[data-fab-count]");

    function activeCount() {
        var c = selections.length;
        if (preset.gu) c++;
        if (preset.area.length) c++;
        if (preset.household) c++;
        if (preset.price) c++;
        return c;
    }

    function renderTray() {
        var n = selections.length;
        trayCount.textContent = n;
        var total = activeCount();
        fabCount.textContent = total;
        trayList.innerHTML = "";

        selections.forEach(function (s, i) {
            var li = document.createElement("li");
            li.className = "hg-tray-item";
            li.innerHTML =
                '<span class="hg-tray-order">' + (i + 1) + "</span>" +
                '<div class="hg-tray-item-main"><b>' + escapeHtml(s.label) + "</b>" +
                (s.sub ? "<span>" + escapeHtml(s.sub) + "</span>" : "") + "</div>" +
                '<button class="hg-tray-remove" aria-label="제거">×</button>';
            li.querySelector(".hg-tray-remove").addEventListener("click", function () {
                removeSelection(s.selId);
            });
            trayList.appendChild(li);
        });

        var show = total > 0;
        tray.hidden = !show;
        trayFab.hidden = !show;
    }

    document.querySelector("[data-tray-reset]").addEventListener("click", function () {
        selections = [];
        preset = { gu: "", dong: "", area: [], household: "", price_type: "trade", price: "" };
        updatePresetLabels();
        syncSelections();
    });

    document.querySelector("[data-explore-btn]").addEventListener("click", goExplore);
    trayFab.addEventListener("click", goExplore);

    function goExplore() {
        var p = new URLSearchParams();
        if (preset.gu) p.set("gu", preset.gu);
        if (preset.dong) p.set("dong", preset.dong);
        preset.area.forEach(function (a) { p.append("area", a); });
        if (preset.household) p.set("household", preset.household);
        if (preset.price) { p.set("price_type", preset.price_type); p.set("price", preset.price); }

        selections.forEach(function (s) {
            if (s.kind === "priority") p.append("priority", s.category + ":" + s.subtype);
            else if (s.kind === "param") p.set(s.param, s.value);
            else if (s.kind === "toggle") p.set(s.param, "1");
        });

        var qs = p.toString();
        if (!qs) return;
        showLoading();
        window.location.href = "/explore?" + qs;
    }

    function showLoading() {
        var ov = document.getElementById("homeLoadingOverlay");
        if (ov) ov.classList.remove("is-hidden");
    }
    function hideLoading() {
        var ov = document.getElementById("homeLoadingOverlay");
        if (ov) ov.classList.add("is-hidden");
    }
    // 뒤로가기(bfcache 복원) 시 로딩 오버레이가 남아 화면을 가리는 문제 방지
    window.addEventListener("pageshow", function () { hideLoading(); });

    /* ---------- 프리셋 바 ---------- */
    var presets = CONFIG.presets || {};
    var presetPanel = null;

    document.querySelectorAll("[data-preset]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            openPresetPanel(btn.getAttribute("data-preset"), btn);
        });
    });
    document.addEventListener("click", function () { closePresetPanel(); });

    function closePresetPanel() {
        if (presetPanel) { presetPanel.remove(); presetPanel = null; }
    }

    function openPresetPanel(kind, anchor) {
        closePresetPanel();
        var panel = document.createElement("div");
        panel.className = "hg-preset-panel";
        panel.addEventListener("click", function (e) { e.stopPropagation(); });

        if (kind === "gu") buildGuPanel(panel);
        else if (kind === "area") buildAreaPanel(panel);
        else if (kind === "household") buildHouseholdPanel(panel);
        else if (kind === "price") buildPricePanel(panel);

        document.body.appendChild(panel);
        var r = anchor.getBoundingClientRect();
        var top = r.bottom + 8;
        var left = Math.min(r.left, window.innerWidth - panel.offsetWidth - 12);
        panel.style.top = top + "px";
        panel.style.left = Math.max(12, left) + "px";
        presetPanel = panel;
    }

    function buildGuPanel(panel) {
        panel.innerHTML = "<h4>지역</h4>";
        var guSel = document.createElement("select");
        guSel.innerHTML = '<option value="">구 전체</option>' +
            (presets.gu || []).map(function (g) {
                return '<option value="' + escapeAttr(g) + '"' + (preset.gu === g ? " selected" : "") + ">" + escapeHtml(g) + "</option>";
            }).join("");
        panel.appendChild(guSel);

        var dongSel = document.createElement("select");
        dongSel.innerHTML = '<option value="">동 전체</option>';
        panel.appendChild(dongSel);

        function loadDongs(gu, keep) {
            fetch("/api/options/dongs?gu=" + encodeURIComponent(gu || "")).then(function (r) { return r.json(); }).then(function (data) {
                dongSel.innerHTML = '<option value="">동 전체</option>' +
                    (data.items || []).map(function (it) {
                        return '<option value="' + escapeAttr(it.value) + '"' + (keep === it.value ? " selected" : "") + ">" + escapeHtml(it.label) + "</option>";
                    }).join("");
            });
        }
        if (preset.gu) loadDongs(preset.gu, preset.dong);

        // 즉시 적용. 단일선택인 지역은 '동'을 고른 순간 패널을 닫는다.
        guSel.addEventListener("change", function () {
            preset.gu = guSel.value; preset.dong = "";
            loadDongs(guSel.value, "");
            updatePresetLabels(); renderTray();
        });
        dongSel.addEventListener("change", function () {
            preset.dong = dongSel.value;
            updatePresetLabels(); renderTray();
            closePresetPanel();   // 선택 완료 → 닫힘
        });
    }

    function buildChipPanel(panel, title, items, getOn, onToggle, opts) {
        opts = opts || {};
        panel.innerHTML = "<h4>" + escapeHtml(title) + "</h4>";
        var grid = document.createElement("div");
        grid.className = "hg-chip-grid";
        items.forEach(function (it) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "hg-chip" + (getOn(it) ? " is-on" : "");
            chip.textContent = it.label;
            chip.addEventListener("click", function () {
                onToggle(it);
                chip.classList.toggle("is-on");
                updatePresetLabels(); renderTray();   // 즉시 적용
                if (opts.singleClose) closePresetPanel();   // 단일선택 → 선택 즉시 닫힘
            });
            grid.appendChild(chip);
        });
        panel.appendChild(grid);
        if (opts.done) addDoneButton(panel);   // 복수선택 → '선택' 버튼으로 닫기
    }

    // 복수선택 패널용 '선택' 버튼(우측 하단)
    function addDoneButton(panel) {
        var actions = document.createElement("div");
        actions.className = "hg-panel-actions";
        actions.innerHTML = '<span></span><button type="button" class="hg-panel-apply">선택</button>';
        panel.appendChild(actions);
        actions.querySelector(".hg-panel-apply").addEventListener("click", closePresetPanel);
    }

    function buildAreaPanel(panel) {
        buildChipPanel(panel, "전용면적 (복수선택 가능)", presets.area || [],
            function (it) { return preset.area.indexOf(it.key) >= 0; },
            function (it) {
                var i = preset.area.indexOf(it.key);
                if (i >= 0) preset.area.splice(i, 1); else preset.area.push(it.key);
            },
            { done: true });   // 복수선택 → '선택' 버튼
    }

    function buildHouseholdPanel(panel) {
        buildChipPanel(panel, "세대수 (단일 선택)", presets.household || [],
            function (it) { return preset.household === it.key; },
            function (it) { preset.household = (preset.household === it.key) ? "" : it.key; },
            { singleClose: true });   // 단일선택 → 선택 즉시 닫힘
        // 단일 선택: 다른 칩 해제
        panel.querySelectorAll(".hg-chip").forEach(function (chip) {
            chip.addEventListener("click", function () {
                panel.querySelectorAll(".hg-chip").forEach(function (c) { if (c !== chip) c.classList.remove("is-on"); });
            });
        });
    }

    function buildPricePanel(panel) {
        panel.innerHTML = "<h4>실거래가</h4>";
        var typeSel = document.createElement("select");
        typeSel.innerHTML = (presets.price_types || []).map(function (t) {
            return '<option value="' + t.key + '"' + (preset.price_type === t.key ? " selected" : "") + ">" + escapeHtml(t.label) + "</option>";
        }).join("");
        panel.appendChild(typeSel);

        var grid = document.createElement("div");
        grid.className = "hg-chip-grid";
        panel.appendChild(grid);

        function renderBuckets() {
            var pt = (presets.price_types || []).filter(function (t) { return t.key === typeSel.value; })[0];
            grid.innerHTML = "";
            (pt ? pt.buckets : []).forEach(function (b) {
                var chip = document.createElement("button");
                chip.type = "button";
                chip.className = "hg-chip" + (preset.price === b.key && preset.price_type === typeSel.value ? " is-on" : "");
                chip.textContent = b.label;
                chip.addEventListener("click", function () {
                    grid.querySelectorAll(".hg-chip").forEach(function (c) { c.classList.remove("is-on"); });
                    var wasOn = (preset.price === b.key && preset.price_type === typeSel.value);
                    if (wasOn) {
                        preset.price = "";
                    } else {
                        preset.price = b.key; preset.price_type = typeSel.value;
                        chip.classList.add("is-on");
                    }
                    updatePresetLabels(); renderTray();   // 즉시 적용
                    if (!wasOn) closePresetPanel();        // 구간 선택 완료 → 닫힘
                });
                grid.appendChild(chip);
            });
        }
        typeSel.addEventListener("change", function () {
            preset.price = ""; preset.price_type = typeSel.value;
            renderBuckets(); updatePresetLabels(); renderTray();
        });
        renderBuckets();
    }

    function updatePresetLabels() {
        setPresetLabel("gu", preset.gu ? (preset.gu + (preset.dong ? " " + preset.dong : "")) : "지역", !!preset.gu);
        setPresetLabel("area", preset.area.length ? labelsFor(presets.area, preset.area) : "전용면적", !!preset.area.length);
        setPresetLabel("household", preset.household ? labelFor(presets.household, preset.household) : "세대수", !!preset.household);
        setPresetLabel("price", preset.price ? priceLabel() : "실거래가", !!preset.price);
    }
    function priceLabel() {
        var pt = (presets.price_types || []).filter(function (t) { return t.key === preset.price_type; })[0];
        if (!pt) return "실거래가";
        var b = pt.buckets.filter(function (x) { return x.key === preset.price; })[0];
        return (preset.price_type === "jeonse" ? "전세 · " : "매매 · ") + (b ? b.label : "");
    }
    function labelFor(list, key) {
        var f = (list || []).filter(function (x) { return x.key === key; })[0];
        return f ? f.label : key;
    }
    function labelsFor(list, keys) {
        var arr = keys.map(function (k) { return labelFor(list, k); });
        return arr.length > 1 ? arr[0] + " 외 " + (arr.length - 1) : arr[0];
    }
    function setPresetLabel(kind, text, on) {
        var el = document.querySelector('[data-preset-label="' + kind + '"]');
        if (el) el.textContent = text;
        var btn = document.querySelector('[data-preset="' + kind + '"]');
        if (btn) btn.classList.toggle("is-set", !!on);
    }

    /* ---------- 상단 아파트명 검색 ---------- */
    var nameForm = document.querySelector("[data-name-search]");
    var nameInput = nameForm.querySelector("[data-name-input]");
    var nameMenu = nameForm.querySelector("[data-name-menu]");
    var nameDebounce = null;

    var nameActive = -1;   // 키보드 하이라이트 인덱스

    function nameButtons() { return Array.prototype.slice.call(nameMenu.querySelectorAll("button")); }
    function setNameActive(idx) {
        var btns = nameButtons();
        if (!btns.length) return;
        nameActive = (idx + btns.length) % btns.length;
        btns.forEach(function (b, i) { b.classList.toggle("is-active", i === nameActive); });
        btns[nameActive].scrollIntoView({ block: "nearest" });
    }
    function pickName(btn) {
        nameInput.value = btn.getAttribute("data-v");
        nameMenu.hidden = true;
        showLoading();
        nameForm.submit();
    }

    nameInput.addEventListener("input", function () {
        clearTimeout(nameDebounce);
        nameActive = -1;
        var q = nameInput.value.trim();
        if (!q) { nameMenu.hidden = true; return; }
        nameDebounce = setTimeout(function () {
            fetch("/api/search/apartments?q=" + encodeURIComponent(q) + "&limit=12")
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var items = data.items || [];
                    if (!items.length) { nameMenu.hidden = true; return; }
                    nameMenu.innerHTML = items.map(function (it) {
                        return '<button type="button" data-v="' + escapeAttr(it.value) + '">' +
                            escapeHtml(it.label) +
                            (it.meta ? '<span class="hg-menu-meta">' + escapeHtml(it.meta) + "</span>" : "") + "</button>";
                    }).join("");
                    nameMenu.hidden = false;
                    nameActive = -1;
                    nameMenu.querySelectorAll("button").forEach(function (b) {
                        b.addEventListener("click", function () { pickName(b); });
                        b.addEventListener("mousemove", function () {
                            var btns = nameButtons(); nameActive = btns.indexOf(b);
                            btns.forEach(function (x, i) { x.classList.toggle("is-active", i === nameActive); });
                        });
                    });
                });
        }, 200);
    });

    // ↓ ↑ 로 이동, Enter 로 선택, Esc 로 닫기
    nameInput.addEventListener("keydown", function (e) {
        if (nameMenu.hidden) return;
        var btns = nameButtons();
        if (e.key === "ArrowDown") { e.preventDefault(); setNameActive(nameActive + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setNameActive(nameActive - 1); }
        else if (e.key === "Enter") {
            if (nameActive >= 0 && btns[nameActive]) { e.preventDefault(); pickName(btns[nameActive]); }
            // 하이라이트가 없으면 폼 기본 submit(아래 submit 핸들러가 로딩 표시)
        } else if (e.key === "Escape") { nameMenu.hidden = true; nameActive = -1; }
    });

    nameForm.addEventListener("submit", function () { showLoading(); });
    document.addEventListener("click", function (e) {
        if (!nameForm.contains(e.target)) nameMenu.hidden = true;
    });

    /* ---------- 리사이즈 ---------- */
    window.addEventListener("resize", function () {
        W = stage.clientWidth; H = stage.clientHeight;
        cx = W / 2; cy = H / 2;
        center.fx = cx; center.fy = cy;
        sim.force("radial").x(cx).y(cy);
        sim.force("x").x(cx);
        sim.force("y").y(cy);
        sim.alpha(0.3).restart();
    });

    /* ---------- 유틸 ---------- */
    function hexA(hex, a) {
        var h = hex.replace("#", "");
        if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
        var r = parseInt(h.substr(0, 2), 16), g = parseInt(h.substr(2, 2), 16), b = parseInt(h.substr(4, 2), 16);
        return "rgba(" + r + "," + g + "," + b + "," + a + ")";
    }
    function escapeHtml(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }
    function escapeAttr(s) { return escapeHtml(s); }

    /* ---------- 방사형 트리 초기 시딩 (가지 엉킴 방지) ---------- */
    function childrenOf(id) {
        return nodes.filter(function (n) { return n.parentId === id; });
    }
    function placeAt(node, angle, r) {
        node._angle = angle;
        node.x = cx + Math.cos(angle) * r;
        node.y = cy + Math.sin(angle) * r;
        node.vx = 0; node.vy = 0;
    }
    function spreadAround(arr, centerAngle, sector, r) {
        if (!arr.length) return;
        if (arr.length === 1) { placeAt(arr[0], centerAngle, r); return; }
        var start = centerAngle - sector / 2, step = sector / (arr.length - 1);
        arr.forEach(function (node, j) { placeAt(node, start + step * j, r); });
    }
    function radialSeed() {
        center.x = cx; center.y = cy; center.fx = cx; center.fy = cy;
        var doms = nodes.filter(function (n) { return n.depth === 1; });
        var n = doms.length || 1;
        doms.forEach(function (dom, i) {
            var a = (i / n) * 2 * Math.PI - Math.PI / 2;     // 12시 방향부터 균등 배치
            placeAt(dom, a, RING[1]);
            // 도메인의 depth-2 자식(카테고리 또는 평탄화 리프)을 도메인 섹터 안에 부채꼴로
            var kids = childrenOf(dom.id);
            spreadAround(kids, a, (2 * Math.PI / n) * 0.82, RING[2]);
        });
    }

    /* ---------- 초기 렌더 ---------- */
    updatePresetLabels();
    radialSeed();      // restart 전에 시딩 → 진입 시 깔끔한 방사형 펼침
    restart(0.9);

    // 살짝 줌아웃해서 전체가 보이도록
    setTimeout(function () {
        var k = Math.min(1, Math.min(W, H) / 980);
        svg.transition().duration(600).call(zoom.transform,
            d3.zoomIdentity.translate(cx * (1 - k), cy * (1 - k)).scale(k));
    }, 200);

})();
