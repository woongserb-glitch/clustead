"""Billboard contract tests using a synthetic, temporary offline artifact.

Run: python tests/test_home_billboard.py
The app may preload local baselines at import; HTTP requests must not open CSVs.
"""

import builtins
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")

from services import home_billboard_service as billboard


def ranking_fixture():
    """Independent records: no production ranking JSON or CSVs are needed."""
    data = {
        "schema_version": 1,
        "data_month": "2026-09",
        "generated_at": "2026-10-01T00:00:00+00:00",
        "complex_count": 2886,
        "sources": {
            key: {"name": f"검증용 {key} 원천", "collected_at": "2026-09-30"}
            for key in ("academy", "subway", "cafe", "convenience", "nightlife",
                        "medical", "transactions", "master")
        },
        "definitions": {},
        "new_complexes": [{"name": "신규검증단지", "gu": "강남구", "dong": "도곡동",
                           "households": 1200, "built": "2026.09"}],
        "er_changes": [{"name": "응급실변경검증단지", "gu": "강남구", "dong": "도곡동",
                        "hospital": "검증응급병원", "distance": 300}],
        "changes_meta": {"master_compared": True, "er_compared": True},
    }
    for key, *_ in billboard.TOPICS:
        data["definitions"][key] = [
            ["기준점", f"{key} 검증 기준: 단지 대표 좌표 또는 법정동 주소"],
            ["반경", "1,000m 직선거리 (도보 아님)"],
            ["방식", "개수 기준 또는 최근접 거리 기준"],
            ["동률", "정의된 보조 지표 이후 원본 입력 순서 유지"],
            ["출처", "검증용 원천 · 수집일 2026-09-30"],
        ]
        rows = []
        for index in range(1, 26 if key == "gu_best_dong" else 51):
            row = {"name": f"{key}검증단지{index:02}", "gu": "강남구",
                   "dong": f"검증동{index:02}", "households": 1200,
                   "station": "검증역", "nearest": "검증역", "hospital": "검증종합병원", "line_names": ["2호선"]}
            row.update({field: 1000 - index for field in billboard.NUMERIC_FIELDS[key]})
            if key == "price_down":
                row["change_pct"] = -row["change_pct"]
            rows.append(row)
        data[key] = rows
    data["definitions"]["changes"] = [
        ["기준", "직전 달과 단지 등록·1km 응급실 변경 비교"],
        ["출처", "검증용 단지·의료 원천"],
    ]
    return data


class RenderedPage(HTMLParser):
    """Inspect actual server-rendered rows and JSON-LD without a browser."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.row_urls = []
        self.links = []
        self.canonical = None
        self.json_ld = []
        self._row = False
        self._json = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "li" and "data-ranking-row" in attrs:
            self._row = True
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
            if self._row and "data-row-link" in attrs:
                self.row_urls.append(attrs["href"])
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs["href"]
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self._json = []

    def handle_data(self, data):
        if self._json is not None:
            self._json.append(data)

    def handle_endtag(self, tag):
        if tag == "li":
            self._row = False
        if tag == "script" and self._json is not None:
            self.json_ld.append(json.loads("".join(self._json)))
            self._json = None


def schema_nodes(value):
    """JSON-LD permits a top-level array, nested mainEntity, or @graph."""
    if isinstance(value, dict):
        if "@type" in value:
            yield value
        for child in value.values():
            yield from schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_nodes(child)


class ArtifactSchemaTests(unittest.TestCase):
    def test_valid_artifact_and_unknown_collection_date(self):
        data = ranking_fixture()
        self.assertIs(billboard.validate_rankings(data), data)
        data["sources"]["academy"]["collected_at"] = None
        billboard.validate_rankings(data)

    def test_rejects_incomplete_metadata_and_invalid_values(self):
        cases = [
            ("schema version", lambda d: d.update(schema_version=2)),
            ("month", lambda d: d.update(data_month="2026-13")),
            ("timestamp", lambda d: d.update(generated_at="not-a-date")),
            ("coverage string", lambda d: d.update(complex_count="2886")),
            ("coverage bool", lambda d: d.update(complex_count=True)),
            ("coverage negative", lambda d: d.update(complex_count=-1)),
            ("sources missing", lambda d: d.pop("sources")),
            ("source missing", lambda d: d["sources"].pop("academy")),
            ("source date missing", lambda d: d["sources"]["academy"].pop("collected_at")),
            ("source date invalid", lambda d: d["sources"]["academy"].update(collected_at="2026-02-30")),
            ("definition empty", lambda d: d["definitions"].update(academy=[])),
            ("definition malformed", lambda d: d["definitions"].update(academy=[["기준", 1]])),
            ("changes definition missing", lambda d: d["definitions"].pop("changes")),
            ("name empty", lambda d: d["academy"][0].update(name=" ")),
            ("duplicate identity", lambda d: d["academy"].__setitem__(1, dict(d["academy"][0]))),
            ("too many rows", lambda d: d["academy"].append(dict(d["academy"][0]))),
            ("numeric string", lambda d: d["academy"][0].update(total="999")),
            ("numeric bool", lambda d: d["academy"][0].update(total=True)),
            ("numeric negative", lambda d: d["academy"][0].update(total=-1)),
            ("numeric nan", lambda d: d["academy"][0].update(total=float("nan"))),
            ("numeric infinity", lambda d: d["academy"][0].update(total=float("inf"))),
            ("station missing", lambda d: d["value_combo"][0].pop("station")),
            ("nearest missing", lambda d: d["subway"][0].pop("nearest")),
            ("hospital missing", lambda d: d["emergency"][0].pop("hospital")),
            ("new households missing", lambda d: d["new_complexes"][0].pop("households")),
            ("er hospital missing", lambda d: d["er_changes"][0].pop("hospital")),
            ("er distance negative", lambda d: d["er_changes"][0].update(distance=-1)),
            ("comparison bool", lambda d: d["changes_meta"].update(master_compared="true")),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                data = ranking_fixture()
                mutate(data)
                with self.assertRaises((ValueError, TypeError, KeyError)):
                    billboard.validate_rankings(data)

    def test_config_defaults_and_limit_bounds(self):
        app = SimpleNamespace(config={}, root_path=str(ROOT))
        billboard.configure(app, lambda key, default: default)
        self.assertTrue(app.config["HOME_BILLBOARD_ENABLED"])
        self.assertTrue(app.config["HOME_MOBILE_ENABLED"])
        # 2026-10-01 사용자 결정: 카카오 순위 공개, 순위 페이지 20위
        self.assertTrue(app.config["HOME_KAKAO_RANKINGS_ENABLED"])
        self.assertEqual(app.config["HOME_RANKING_LIMIT"], 20)
        for supplied, expected in (("10", 20), ("99", 50), ("invalid", 20)):
            with self.subTest(limit=supplied):
                billboard.configure(app, lambda key, default: supplied if key == "HOME_RANKING_LIMIT" else default)
                self.assertEqual(app.config["HOME_RANKING_LIMIT"], expected)


class BillboardRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.module = app
        cls.app = app.app

    def setUp(self):
        self.saved_config = dict(self.app.config)
        self.temp = tempfile.TemporaryDirectory(prefix="clustead-billboard-test-")
        self.path = Path(self.temp.name) / "rankings.json"
        self.data = ranking_fixture()
        self.write_artifact(self.data)
        self.app.config.update(
            TESTING=True, HOME_BILLBOARD_ENABLED=True, HOME_GRAPH_ENABLED=True,
            HOME_MOBILE_ENABLED=True, HOME_KAKAO_RANKINGS_ENABLED=False,
            HOME_RANKING_PAGES_ENABLED=True, HOME_RANKING_LIMIT=30,
            HOME_RANKINGS_PATH=str(self.path),
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.config.clear()
        self.app.config.update(self.saved_config)
        billboard.load_rankings.cache_clear()
        self.temp.cleanup()

    def write_artifact(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        billboard.load_rankings.cache_clear()

    def get_html(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.get_data(as_text=True)

    def sitemap_urls(self):
        xml = ElementTree.fromstring(self.get_html("/sitemap.xml"))
        return [node.text for node in xml.findall("{*}url/{*}loc")]

    def test_home_has_top_five_links_and_criteria_without_javascript(self):
        html = self.get_html("/")
        self.assertIn("data-billboard", html)
        self.assertIn("2026-09", html)
        self.assertNotIn("학군", html)
        for key in ("academy", "dong_academy", "value_combo", "subway", "quiet", "emergency"):
            with self.subTest(topic=key):
                card = re.search(rf'<article\b[^>]*id="topic-{key}"[^>]*>(.*?)</article>', html, re.S)
                self.assertIsNotNone(card)
                rows = RenderedPage(card.group(1)).row_urls
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(url.startswith("/area/" if key == "dong_academy" else "/apartments/") for url in rows))
                for label, text in self.data["definitions"][key]:
                    self.assertIn(label, card.group(1))
                    self.assertIn(text, card.group(1))
        self.assertIn("신규검증단지", html)
        self.assertIn("검증응급병원", html)

    def test_rankings_json_ld_matches_server_rows_and_canonical(self):
        for key, slug, _, title, _ in billboard.TOPICS:
            if key in ("starbucks", "convenience"):
                continue
            with self.subTest(topic=key):
                path = f"/rankings/{slug}"
                html = self.get_html(path + "?src=share&share_q=discard")
                page = RenderedPage(html)
                self.assertEqual(urlsplit(page.canonical).path, path)
                self.assertEqual(urlsplit(page.canonical).query, "")
                self.assertIn(title + " | Clustead</title>", html)
                self.assertIn('name="description"', html)
                item_list = next(node for node in page.json_ld if node.get("@type") == "ItemList")
                expected_count = 25 if key == "gu_best_dong" else 30
                self.assertEqual(len(page.row_urls), expected_count)
                self.assertEqual(item_list["numberOfItems"], expected_count)
                self.assertEqual([row["position"] for row in item_list["itemListElement"]], list(range(1, expected_count + 1)))
                self.assertEqual([row["url"] for row in item_list["itemListElement"]],
                                 [urljoin(page.canonical, url) for url in page.row_urls])
                for _, criterion in self.data["definitions"][key]:
                    self.assertIn(criterion, html)

    def test_home_collection_schema_matches_visible_topic_links_and_flags(self):
        for pages, kakao in ((True, False), (True, True), (False, False)):
            with self.subTest(pages=pages, kakao=kakao):
                self.app.config.update(HOME_RANKING_PAGES_ENABLED=pages, HOME_KAKAO_RANKINGS_ENABLED=kakao)
                page = RenderedPage(self.get_html("/?src=share"))
                nodes = list(schema_nodes(page.json_ld))
                self.assertTrue(any(node["@type"] == "WebSite" for node in nodes))
                self.assertTrue(any(node["@type"] == "Organization" for node in nodes))
                collection = next(node for node in nodes if node["@type"] == "CollectionPage")
                self.assertEqual(collection["url"], page.canonical)
                lists = [node for node in schema_nodes(collection) if node["@type"] == "ItemList"]
                elements = [entry for item_list in lists for entry in item_list["itemListElement"]]
                ld_urls = {entry.get("url") or entry["item"]["url"] for entry in elements}
                visible_urls = {urljoin(page.canonical, url) for url in page.links if url.startswith("/rankings/")}
                self.assertEqual(ld_urls, visible_urls)
                for item_list in lists:
                    self.assertEqual(item_list["numberOfItems"], len(item_list["itemListElement"]))
                if not pages:
                    self.assertEqual(ld_urls, set())
                self.assertEqual(any(urlsplit(url).path == "/rankings/starbucks" for url in ld_urls), pages and kakao)

    def test_ranking_answer_and_source_summary_are_server_rendered(self):
        with self.app.test_request_context("/"):
            view = self.module.build_billboard_context()["billboard"]
        for topic in view["topics"]:
            with self.subTest(topic=topic["key"]):
                html = self.get_html(topic["url"])
                body = html.split("</head>", 1)[1]
                self.assertTrue(topic["answer"].strip())
                self.assertIn(escape(topic["answer"], quote=False), body)
                self.assertTrue(topic["source_summary"].strip())
                self.assertIn(escape(topic["source_summary"], quote=False), body)
        academy_html = self.get_html("/rankings/academy-apartments")
        self.assertIn("2,886", self.get_html("/"))
        self.assertIn("academy검증단지01", academy_html)
        self.assertIn("999", academy_html)
        self.assertIn("2026-09", academy_html)

    def test_monthly_changes_keep_all_records_and_matching_json_ld(self):
        self.app.config["HOME_RANKING_LIMIT"] = 20
        self.data["new_complexes"] = [
            {**self.data["new_complexes"][0], "name": f"신규검증단지{index:02}"}
            for index in range(35)
        ]
        self.data["er_changes"] = [
            {**self.data["er_changes"][0], "name": f"응급실변경검증단지{index:02}"}
            for index in range(2)
        ]
        self.write_artifact(self.data)
        html = self.get_html("/rankings/monthly-changes")
        page = RenderedPage(html)
        self.assertEqual(len(page.row_urls), 37)
        self.assertIn("응급실변경검증단지01", html)
        self.assertNotIn("TOP 20", html)
        item_list = next(node for node in schema_nodes(page.json_ld) if node["@type"] == "ItemList")
        self.assertEqual(item_list["numberOfItems"], 37)
        self.assertEqual([row["url"] for row in item_list["itemListElement"]],
                         [urljoin(page.canonical, url) for url in page.row_urls])

    def test_configured_top_n_clamps_to_twenty_through_fifty(self):
        for configured, expected in ((10, 20), (20, 20), (40, 40), (60, 50)):
            with self.subTest(limit=configured):
                self.app.config["HOME_RANKING_LIMIT"] = configured
                page = RenderedPage(self.get_html("/rankings/academy-apartments"))
                self.assertEqual(len(page.row_urls), expected)

    def test_kakao_topics_are_hidden_from_all_public_surfaces_until_enabled(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.app.config["HOME_KAKAO_RANKINGS_ENABLED"] = enabled
                home = self.get_html("/")
                sibling = self.get_html("/rankings/academy-apartments")
                sitemap = self.sitemap_urls()
                home_ld = json.dumps(RenderedPage(home).json_ld, ensure_ascii=False)
                for key, slug in (("starbucks", "starbucks"), ("convenience", "convenience-stores")):
                    self.assertEqual(f'id="topic-{key}"' in home, enabled)
                    self.assertEqual(f"/rankings/{slug}" in sibling, enabled)
                    self.assertEqual(any(urlsplit(url).path == f"/rankings/{slug}" for url in sitemap), enabled)
                    self.assertEqual(self.client.get(f"/rankings/{slug}").status_code, 200 if enabled else 404)
                    if not enabled:
                        self.assertNotIn(f"{key}검증단지", home)
                        self.assertNotIn(f"{key}검증단지", home_ld)

    def test_decision_flags_control_graph_mobile_pages_and_home_fallback(self):
        self.assertIn('href="/graph"', self.get_html("/"))
        self.assertIn('id="home-config"', self.get_html("/graph"))
        self.app.config["HOME_GRAPH_ENABLED"] = False
        self.assertNotIn('href="/graph"', self.get_html("/"))
        self.assertEqual(self.client.get("/graph").status_code, 404)
        self.assertNotIn("location.replace('/explore'", self.get_html("/"))
        self.app.config["HOME_MOBILE_ENABLED"] = False
        self.assertIn("location.replace('/explore'", self.get_html("/"))
        self.app.config["HOME_RANKING_PAGES_ENABLED"] = False
        self.assertNotIn('href="/rankings/', self.get_html("/"))
        self.assertEqual(self.client.get("/rankings/academy-apartments").status_code, 404)
        self.assertFalse(any("/rankings/" in url for url in self.sitemap_urls()))
        self.app.config["HOME_BILLBOARD_ENABLED"] = False
        old_home = self.get_html("/")
        self.assertIn('id="home-config"', old_home)
        self.assertNotIn("data-billboard", old_home)

    def test_sitemap_only_lists_canonical_ranking_urls(self):
        self.get_html("/?src=share&home=billboard")
        self.get_html("/rankings/academy-apartments?src=share&q=ignored")
        urls = self.sitemap_urls()
        self.assertEqual(len(urls), len(set(urls)))
        self.assertTrue(any(urlsplit(url).path == "/rankings/academy-apartments" for url in urls))
        for url in urls:
            self.assertEqual(urlsplit(url).query, "", url)
            self.assertEqual(urlsplit(url).fragment, "", url)
            self.assertNotIn("/result?", url)

    def test_billboard_sitemap_lastmod_comes_from_offline_artifact(self):
        # Baseline mtime is unrelated to when this independent artifact changed.
        with patch.object(self.module, "DATA_LASTMOD", "2020-01-01"):
            xml = ElementTree.fromstring(self.get_html("/sitemap.xml"))
        checked = 0
        for entry in xml.findall("{*}url"):
            path = urlsplit(entry.find("{*}loc").text).path
            if path == "/" or path.startswith("/rankings/"):
                self.assertEqual(entry.find("{*}lastmod").text, self.data["generated_at"][:10])
                checked += 1
        self.assertGreater(checked, 1)

    def test_requests_read_json_once_and_never_open_csv_even_on_cold_cache(self):
        billboard.load_rankings.cache_clear()
        original_open, original_io_open = builtins.open, io.open
        artifact_reads = []

        def guarded(open_function):
            def open_file(file, *args, **kwargs):
                if isinstance(file, (str, bytes, os.PathLike)):
                    path = os.fsdecode(file)
                    if path.lower().endswith(".csv"):
                        raise AssertionError(f"Request opened a CSV: {path}")
                    if Path(path) == self.path:
                        artifact_reads.append(path)
                return open_function(file, *args, **kwargs)
            return open_file

        with patch("builtins.open", guarded(original_open)), patch("io.open", guarded(original_io_open)):
            for url in ("/", "/rankings/academy-apartments", "/rankings/academy-neighborhoods", "/sitemap.xml", "/"):
                self.get_html(url)
        self.assertEqual(len(artifact_reads), 1)

    def test_missing_corrupt_and_incomplete_artifacts_fail_gracefully(self):
        cases = [
            ("missing", None), ("corrupt", "{broken json"),
            ("source missing", lambda d: d["sources"].pop("academy")),
            ("source date missing", lambda d: d["sources"]["academy"].pop("collected_at")),
            ("station missing", lambda d: d["value_combo"][0].pop("station")),
            ("coverage malformed", lambda d: d.update(complex_count="2886")),
            ("changes malformed", lambda d: d["er_changes"][0].pop("hospital")),
        ]
        for label, change in cases:
            with self.subTest(label=label):
                if change is None:
                    self.path.unlink(missing_ok=True)
                elif isinstance(change, str):
                    self.path.write_text(change, encoding="utf-8")
                else:
                    data = copy.deepcopy(self.data)
                    change(data)
                    self.write_artifact(data)
                billboard.load_rankings.cache_clear()
                html = self.get_html("/")
                self.assertIn("준비", html)
                self.assertNotIn('id="topic-academy"', html)
                self.assertEqual(self.client.get("/rankings/academy-apartments").status_code, 404)
                self.assertFalse(any("/rankings/" in url for url in self.sitemap_urls()))

    def test_unknown_details_and_rankings_keep_not_found_status(self):
        self.assertEqual(self.client.get("/rankings/not-a-topic").status_code, 404)
        unknown = self.module.apartment_detail_path("없는검증단지_zzz", "강남구", "도곡동")
        for enabled in (False, True):
            with self.subTest(billboard=enabled):
                self.app.config["HOME_BILLBOARD_ENABLED"] = enabled
                self.assertEqual(self.client.get(unknown).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
