from collections import Counter, defaultdict
from datetime import date
from difflib import SequenceMatcher
import re

from transaction_layer_utils import (
    TRANSACTION_MAPPING_AUDIT_PATH,
    TRANSACTION_MANUAL_MAPPING_PATH,
    TRANSACTION_MAPPING_PATH,
    TRANSACTION_MASTER_PATH,
    TRANSACTION_REJECT_MAPPING_PATH,
    clean_text,
    compose_lot_number,
    ensure_transaction_dirs,
    normalize_address,
    normalize_dong,
    normalize_lot_part,
    normalize_name,
    read_apartment_master,
    read_csv_rows,
    write_csv,
)


MANUAL_MAPPING_FIELDS = [
    "livefit_name",
    "gu",
    "dong",
    "kapt_code",
    "transaction_apt_name",
    "transaction_bonbun",
    "transaction_bubun",
    "match_type",
    "verified",
    "notes",
    "created_at",
    "auto_approved",
    "approval_reason",
    "approved_at",
]

MAPPING_FIELDS = [
    "livefit_name",
    "kapt_code",
    "kapt_name",
    "gu",
    "dong",
    "road_address",
    "transaction_apt_name",
    "transaction_road_address",
    "transaction_jibun",
    "match_type",
    "match_confidence",
    "manual_override",
    "verified",
    "notes",
]

ALIAS_CANDIDATES_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_alias_candidates.csv")
SAME_LOT_REVIEW_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_same_lot_review.csv")
MISSING_BONBUN_ANALYSIS_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("missing_bonbun_bubun_analysis.csv")
QUICK_REVIEW_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_quick_review.csv")
AUTO_APPROVE_ALIAS_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_auto_approve_alias.csv")
VERIFIED_AUDIT_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_verified_mapping_audit.csv")
VERIFIED_RISK_SUMMARY_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_verified_risk_summary.csv")
RAW_NAME_REVERSE_AUDIT_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_raw_name_reverse_audit.csv")
MANUAL_REVIEW_BATCH_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_manual_review_batch.csv")
MANUAL_REVIEW_BATCH_EXCEL_PATH = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_manual_review_batch_excel.csv")

AUTO_APPROVE_ALIAS_THRESHOLD = 0.92
ROAD_ADDRESS_EXACT_VERIFY_THRESHOLD = 0.60
QUICK_REVIEW_MIN_SCORE = 0.80
QUICK_REVIEW_MAX_SCORE = 0.92

REJECT_MAPPING_FIELDS = [
    "livefit_name",
    "gu",
    "dong",
    "kapt_code",
    "transaction_candidate_name",
    "reject_reason",
    "confirmed_by",
    "confirmed_at",
    "notes",
]


def load_transaction_candidates():
    if not TRANSACTION_MASTER_PATH.exists():
        return []

    rows, _ = read_csv_rows(TRANSACTION_MASTER_PATH)
    seen = {}
    for row in rows:
        apt_name = clean_text(row.get("apartment_name") or row.get("apt_name_raw"))
        if not apt_name:
            continue
        road_address = clean_text(row.get("road_address"))
        road_norm = normalize_address(row.get("normalized_road_address") or road_address)
        road_name = clean_text(row.get("road_name"))
        road_name_norm = normalize_address(road_name)
        bonbun = normalize_lot_part(row.get("bonbun"))
        bubun = normalize_lot_part(row.get("bubun"))
        key = (
            clean_text(row.get("gu")),
            normalize_dong(row.get("dong")),
            normalize_name(apt_name),
            road_norm,
            bonbun,
            bubun,
        )
        candidate = seen.setdefault(key, {
            "transaction_apt_name": apt_name,
            "transaction_road_address": road_address,
            "transaction_jibun": clean_text(row.get("jibun")),
            "gu": clean_text(row.get("gu")),
            "dong": clean_text(row.get("dong")),
            "apt_norm": normalize_name(apt_name),
            "road_norm": road_norm,
            "road_name_norm": road_name_norm,
            "bonbun": bonbun,
            "bubun": bubun,
            "jibun_norm": compose_lot_number(row.get("bonbun"), row.get("bubun")) or normalize_address(row.get("jibun")),
            "trade_count": 0,
            "rent_count": 0,
            "transaction_count": 0,
        })
        transaction_type = clean_text(row.get("transaction_type")).lower()
        if transaction_type == "trade":
            candidate["trade_count"] += 1
        elif transaction_type == "rent":
            candidate["rent_count"] += 1
        candidate["transaction_count"] += 1
    return list(seen.values())


def load_manual_overrides():
    if not TRANSACTION_MANUAL_MAPPING_PATH.exists():
        write_csv(TRANSACTION_MANUAL_MAPPING_PATH, [], MANUAL_MAPPING_FIELDS)
        return {}
    rows, _ = read_csv_rows(TRANSACTION_MANUAL_MAPPING_PATH)
    with TRANSACTION_MANUAL_MAPPING_PATH.open(encoding="utf-8-sig") as handle:
        existing_fields = [field.strip() for field in handle.readline().strip().split(",") if field.strip()]
    if any(field not in existing_fields for field in MANUAL_MAPPING_FIELDS):
        write_csv(TRANSACTION_MANUAL_MAPPING_PATH, rows, MANUAL_MAPPING_FIELDS)
    overrides = {}
    for row in rows:
        name = clean_text(row.get("livefit_name"))
        verified = clean_text(row.get("verified")).upper()
        if name and verified == "Y":
            overrides[name] = row
    return overrides


def load_reject_overrides():
    if not TRANSACTION_REJECT_MAPPING_PATH.exists():
        write_csv(TRANSACTION_REJECT_MAPPING_PATH, [], REJECT_MAPPING_FIELDS)
        return set()
    rows, _ = read_csv_rows(TRANSACTION_REJECT_MAPPING_PATH)
    with TRANSACTION_REJECT_MAPPING_PATH.open(encoding="utf-8-sig") as handle:
        existing_fields = [field.strip() for field in handle.readline().strip().split(",") if field.strip()]
    if any(field not in existing_fields for field in REJECT_MAPPING_FIELDS):
        write_csv(TRANSACTION_REJECT_MAPPING_PATH, rows, REJECT_MAPPING_FIELDS)
    rejected = set()
    for row in rows:
        livefit_name = clean_text(row.get("livefit_name"))
        candidate_name = clean_text(row.get("transaction_candidate_name"))
        if not livefit_name or not candidate_name:
            continue
        rejected.add((livefit_name, normalize_name(candidate_name)))
    return rejected


def is_rejected_candidate(apartment, candidate, rejected_pairs):
    if not candidate:
        return False
    return (
        apartment["livefit_name"],
        normalize_name(candidate.get("transaction_apt_name", "")),
    ) in rejected_pairs


def reject_excluded_row(apartment, candidate):
    return make_row(
        apartment,
        candidate,
        "manual_reject_excluded",
        "0.00",
        "N",
        "candidate excluded by apartment_transaction_mapping_reject.csv",
    )


def build_indexes(candidates):
    by_road = defaultdict(list)
    by_name = {}
    by_jibun = defaultdict(list)
    by_road_number = defaultdict(list)
    by_dong = defaultdict(list)

    for candidate in candidates:
        if candidate["road_norm"]:
            by_road[(candidate["gu"], candidate["road_norm"])].append(candidate)
        if candidate.get("road_name_norm") and candidate.get("jibun_norm"):
            by_road_number[(candidate["gu"], normalize_dong(candidate["dong"]), candidate["road_name_norm"], candidate["jibun_norm"])].append(candidate)
        if candidate.get("bonbun"):
            by_jibun[(candidate["gu"], normalize_dong(candidate["dong"]), candidate["bonbun"], candidate.get("bubun", ""))].append(candidate)
        if candidate["apt_norm"]:
            by_name[(candidate["gu"], normalize_dong(candidate["dong"]), candidate["apt_norm"])] = candidate
            by_dong[(candidate["gu"], normalize_dong(candidate["dong"]))].append(candidate)

    return by_road, by_name, by_dong, by_jibun, by_road_number


def manual_mapping_row(apartment, override):
    transaction_jibun = clean_text(override.get("transaction_jibun"))
    if not transaction_jibun:
        transaction_jibun = compose_lot_number(
            override.get("transaction_bonbun"),
            override.get("transaction_bubun"),
        )
    return {
        "livefit_name": apartment["livefit_name"],
        "kapt_code": apartment["kapt_code"],
        "kapt_name": apartment["kapt_name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "road_address": apartment["road_address"],
        "transaction_apt_name": clean_text(override.get("transaction_apt_name")),
        "transaction_road_address": clean_text(override.get("transaction_road_address")),
        "transaction_jibun": transaction_jibun,
        "match_type": clean_text(override.get("match_type")) or "manual_alias",
        "match_confidence": "1.00",
        "manual_override": "Y",
        "verified": "Y",
        "notes": clean_text(override.get("notes")),
    }


def make_row(apartment, candidate=None, match_type="", confidence="", verified="N", notes=""):
    return {
        "livefit_name": apartment["livefit_name"],
        "kapt_code": apartment["kapt_code"],
        "kapt_name": apartment["kapt_name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "road_address": apartment["road_address"],
        "transaction_apt_name": candidate.get("transaction_apt_name", "") if candidate else "",
        "transaction_road_address": candidate.get("transaction_road_address", "") if candidate else "",
        "transaction_jibun": candidate.get("transaction_jibun", "") if candidate else "",
        "match_type": match_type,
        "match_confidence": confidence,
        "manual_override": "N",
        "verified": verified,
        "notes": notes,
    }


def auto_approve_mapping_row(apartment, candidate, score, reason):
    row = make_row(apartment, candidate, "AUTO_APPROVE_ALIAS", f"{score:.2f}", "Y", reason)
    row["manual_override"] = "N"
    return row


def transaction_name_similarity(apartment, mapping_or_candidate):
    livefit_norm = normalize_name(apartment.get("livefit_name"))
    candidate_norm = mapping_or_candidate.get("apt_norm") or normalize_name(
        mapping_or_candidate.get("transaction_apt_name", "")
    )
    if not livefit_norm or not candidate_norm:
        return 0
    return SequenceMatcher(None, livefit_norm, candidate_norm).ratio()


def best_road_address_candidate(apartment, candidates):
    if not candidates:
        return None, 0
    scored = sorted(
        candidates,
        key=lambda candidate: (
            transaction_name_similarity(apartment, candidate),
            int(candidate.get("trade_count", 0)) + int(candidate.get("rent_count", 0)),
            candidate.get("transaction_apt_name", ""),
        ),
        reverse=True,
    )
    best = scored[0]
    return best, transaction_name_similarity(apartment, best)


def pick_unique_or_named(
    apartment,
    candidates,
    match_type,
    verified_confidence,
    candidate_confidence,
    require_road_address_score=False,
):
    name_norm = normalize_name(apartment["livefit_name"])
    if require_road_address_score:
        candidate, name_score = best_road_address_candidate(apartment, candidates)
        confidence = verified_confidence if len(candidates) == 1 else candidate_confidence
        try:
            match_score = float(confidence or 0)
        except Exception:
            match_score = 0
        if candidate and road_address_matches(apartment, candidate) and match_score >= ROAD_ADDRESS_EXACT_VERIFY_THRESHOLD:
            candidate_match_type = match_type
            if len(candidates) > 1 and candidate.get("apt_norm") == name_norm:
                candidate_match_type = f"{match_type}_name_confirmed"
            elif len(candidates) > 1:
                candidate_match_type = f"{match_type}_score_verified"
            return make_row(
                apartment,
                candidate,
                candidate_match_type,
                confidence,
                "Y",
                f"normalized road address exact and match_score >= 0.60; name_similarity={name_score:.2f}",
            )
        return make_row(
            apartment,
            candidate,
            f"{match_type}_candidate",
            confidence or "0.00",
            "N",
            "normalized road address exact but match_score below 0.60; manual review needed",
        )

    if len(candidates) == 1:
        return make_row(apartment, candidates[0], match_type, verified_confidence, "Y")
    for candidate in candidates:
        item_norm = candidate.get("apt_norm", "")
        if item_norm and item_norm == name_norm:
            return make_row(apartment, candidate, f"{match_type}_name_confirmed", verified_confidence, "Y")
    for candidate in candidates:
        item_norm = candidate.get("apt_norm", "")
        if len(name_norm) >= 4 and len(item_norm) >= 4 and (name_norm in item_norm or item_norm in name_norm):
            return make_row(
                apartment,
                candidate,
                f"{match_type}_candidate",
                candidate_confidence,
                "N",
                "multiple candidates share this address/lot; verify before using for price-sensitive display",
            )
    return make_row(
        apartment,
        candidates[0] if candidates else None,
        f"{match_type}_ambiguous",
        candidate_confidence,
        "N",
        "multiple candidates share this address/lot; manual review needed",
    )


def match_apartment(apartment, by_road, by_name, by_dong, by_jibun, by_road_number):
    gu = apartment["gu"]
    dong_norm = normalize_dong(apartment["dong"])
    name_norm = normalize_name(apartment["livefit_name"])
    road_norm = normalize_address(apartment["road_address"])
    road_name_norm = normalize_address(apartment.get("road_name"))
    road_detail_norm = normalize_address(apartment.get("road_detail"))
    bonbun = normalize_lot_part(apartment.get("bonbun"))
    bubun = normalize_lot_part(apartment.get("bubun"))

    if road_norm:
        candidates = by_road.get((gu, road_norm), [])
        if candidates:
            return pick_unique_or_named(
                apartment,
                candidates,
                "road_address_exact",
                "0.98",
                "0.86",
                require_road_address_score=True,
            )

    if road_name_norm and road_detail_norm:
        candidates = by_road_number.get((gu, dong_norm, road_name_norm, road_detail_norm), [])
        if candidates:
            return pick_unique_or_named(apartment, candidates, "gu_dong_road_number_exact", "0.97", "0.82")

    if bonbun:
        candidates = by_jibun.get((gu, dong_norm, bonbun, bubun), [])
        if candidates:
            return pick_unique_or_named(apartment, candidates, "gu_dong_jibun_exact", "0.96", "0.80")

    if name_norm:
        candidate = by_name.get((gu, dong_norm, name_norm))
        if candidate:
            if address_validated(apartment, candidate):
                return make_row(apartment, candidate, "gu_dong_name_exact_address_confirmed", "0.94", "Y")
            return make_row(
                apartment,
                candidate,
                "gu_dong_name_exact_candidate",
                "0.72",
                "N",
                "name exact only; road address or lot-number validation required before verified",
            )

    if len(name_norm) >= 4:
        for candidate in by_dong.get((gu, dong_norm), []):
            item_norm = candidate.get("apt_norm", "")
            if len(item_norm) >= 4 and (name_norm in item_norm or item_norm in name_norm):
                return make_row(
                    apartment,
                    candidate,
                    "same_dong_contains_candidate",
                    "0.78",
                    "N",
                    "candidate only; verify before using for price-sensitive display",
                )

    return make_row(apartment, None, "unmatched", "0.00", "N")


def audit_row(mapping_row, apartment, by_dong, by_jibun):
    gu = apartment["gu"]
    dong_norm = normalize_dong(apartment["dong"])
    name_norm = normalize_name(apartment["livefit_name"])
    bonbun = normalize_lot_part(apartment.get("bonbun"))
    bubun = normalize_lot_part(apartment.get("bubun"))
    same_dong_candidates = by_dong.get((gu, dong_norm), [])
    candidates = []
    if bonbun:
        candidates = by_jibun.get((gu, dong_norm, bonbun, bubun), [])
    if not candidates:
        candidates = same_dong_candidates
    best_candidate = None
    if mapping_row.get("transaction_apt_name"):
        best_candidate = {
            "transaction_apt_name": mapping_row.get("transaction_apt_name", ""),
            "transaction_road_address": mapping_row.get("transaction_road_address", ""),
            "transaction_jibun": mapping_row.get("transaction_jibun", ""),
        }
    elif candidates:
        best_candidate = candidates[0]
    candidate_names = []
    best_similarity = 0
    best_similarity_name = ""
    for candidate in candidates:
        name = candidate.get("transaction_apt_name", "")
        if name and name not in candidate_names:
            candidate_names.append(name)
        item_norm = candidate.get("apt_norm", "")
        if name_norm and item_norm:
            score = SequenceMatcher(None, name_norm, item_norm).ratio()
            if score > best_similarity:
                best_similarity = score
                best_similarity_name = name
    if mapping_row["verified"] == "Y":
        status = "verified"
        action = "accept"
    elif mapping_row["match_type"] != "unmatched":
        status = "candidate"
        action = "review_candidate"
    else:
        status = "unmatched"
        action = "manual_mapping_needed"
    reason_type, reason_detail, resolution_bucket = classify_reason(
        mapping_row,
        apartment,
        same_dong_candidates,
        candidates,
        best_similarity,
        best_similarity_name,
    )
    return {
        "livefit_name": mapping_row["livefit_name"],
        "gu": mapping_row["gu"],
        "dong": mapping_row["dong"],
        "road_address": mapping_row["road_address"],
        "livefit_road_address": apartment.get("road_address", ""),
        "transaction_road_address": best_candidate.get("transaction_road_address", "") if best_candidate else "",
        "livefit_bonbun": bonbun,
        "livefit_bubun": bubun,
        "transaction_bonbun": best_candidate.get("bonbun", "") if best_candidate else "",
        "transaction_bubun": best_candidate.get("bubun", "") if best_candidate else "",
        "road_address_match": address_match_value(road_address_matches(apartment, best_candidate or {})),
        "jibun_match": address_match_value(lot_matches(apartment, best_candidate or {})),
        "match_priority_reason": match_priority_reason(apartment, best_candidate or {}, mapping_row.get("match_type", "")),
        "kapt_code": mapping_row["kapt_code"],
        "kapt_name": mapping_row["kapt_name"],
        "current_match_status": status,
        "best_candidate_name": mapping_row["transaction_apt_name"] or (candidate_names[0] if candidate_names else ""),
        "best_candidate_road_address": mapping_row["transaction_road_address"],
        "best_candidate_score": mapping_row["match_confidence"],
        "candidate_names": "; ".join(candidate_names[:20]),
        "candidate_count": len(candidate_names),
        "reason_type": reason_type,
        "reason_detail": reason_detail,
        "resolution_bucket": resolution_bucket,
        "best_name_similarity": f"{best_similarity:.2f}" if best_similarity else "",
        "best_similarity_name": best_similarity_name,
        "recommended_action": action,
        "notes": mapping_row["notes"],
    }


def classify_reason(mapping_row, apartment, same_dong_candidates, scoped_candidates, best_similarity, best_similarity_name):
    match_type = mapping_row.get("match_type", "")
    status = "verified" if mapping_row.get("verified") == "Y" else ("candidate" if match_type != "unmatched" else "unmatched")
    bonbun = normalize_lot_part(apartment.get("bonbun"))
    bubun = normalize_lot_part(apartment.get("bubun"))

    if status == "verified":
        return "MATCHED", "verified mapping; excluded from failure analysis", "auto_resolved"

    if "ambiguous" in match_type or "jibun_exact_candidate" in match_type or len(scoped_candidates) > 1 and bonbun and match_type != "same_dong_contains_candidate":
        return (
            "SAME_LOT_MULTIPLE_COMPLEX",
            "same lot/building key has multiple transaction candidates; manual confirmation is safer",
            "manual_override_needed",
        )

    if status == "candidate":
        if match_type in {"gu_dong_name_exact_candidate", "same_dong_contains_candidate"}:
            return (
                "LOW_CONFIDENCE",
                "name candidate requires road address or lot-number validation",
                "address_validation_needed",
            )
        if "contains" in match_type or best_similarity >= 0.72:
            return (
                "NAME_ALIAS",
                f"name looks related but not exact enough for verified mapping; best={best_similarity_name}",
                "manual_or_alias_table",
            )
        return (
            "LOW_CONFIDENCE",
            "candidate exists but confidence is below verified threshold",
            "manual_review_needed",
        )

    if not same_dong_candidates:
        return (
            "NO_RECENT_TRANSACTION",
            "no transaction apartment candidate found in the same gu/dong raw layer",
            "rawdata_or_no_transaction",
        )

    if not bonbun:
        return (
            "MISSING_BONBUN_BUBUN",
            "LiveFit master lacks usable lot number, and Seoul transaction raw has no road-address key",
            "master_data_cleanup",
        )

    if best_similarity >= 0.72:
        return (
            "NAME_ALIAS",
            f"same-dong candidate has similar name but no exact/contains match; best={best_similarity_name}",
            "manual_or_alias_table",
        )

    if scoped_candidates:
        return (
            "POSSIBLE_MATCH_NEEDS_MANUAL_REVIEW",
            "lot candidate exists but automatic name confirmation failed",
            "manual_review_needed",
        )

    return (
        "ADDRESS_MISMATCH",
        f"same-dong transactions exist, but LiveFit lot {bonbun}-{bubun or '0'} was not found in transaction raw",
        "address_or_transaction_gap",
    )


def candidate_similarity(apartment, candidate):
    name_norm = normalize_name(apartment["livefit_name"])
    item_norm = candidate.get("apt_norm", "")
    if not name_norm or not item_norm:
        return 0
    return SequenceMatcher(None, name_norm, item_norm).ratio()


def normalized_name_numbers(value):
    text = normalize_name(value)
    roman_map = {
        "ⅰ": "1",
        "ⅱ": "2",
        "ⅲ": "3",
        "ⅳ": "4",
        "ⅴ": "5",
        "Ⅰ": "1",
        "Ⅱ": "2",
        "Ⅲ": "3",
        "Ⅳ": "4",
        "Ⅴ": "5",
    }
    for roman, number in roman_map.items():
        text = text.replace(roman.lower(), number)
    return set(part.lstrip("0") or "0" for part in re.findall(r"\d+", text))


def strip_dong_prefix(name, dong):
    name_norm = normalize_name(name)
    dong_norm = normalize_name(dong)
    if not name_norm or not dong_norm:
        return name_norm
    dong_without_suffix = re.sub(r"(동|가|리)$", "", dong_norm)
    for prefix in (dong_norm, dong_without_suffix):
        if prefix and name_norm.startswith(prefix) and len(name_norm) > len(prefix) + 1:
            return name_norm[len(prefix):]
    return name_norm


def is_dong_prefix_alias(apartment, candidate):
    candidate_norm = candidate.get("apt_norm", "")
    if not candidate_norm:
        return False
    livefit_norm = normalize_name(apartment.get("livefit_name", ""))
    prefix_stripped = strip_dong_prefix(apartment.get("livefit_name", ""), apartment.get("dong", ""))
    return prefix_stripped == candidate_norm and livefit_norm != candidate_norm


def has_number_conflict(apartment, candidate):
    livefit_numbers = normalized_name_numbers(apartment["livefit_name"])
    candidate_numbers = normalized_name_numbers(candidate.get("transaction_apt_name", ""))
    if not livefit_numbers or not candidate_numbers:
        return False
    return livefit_numbers != candidate_numbers


def has_number_asymmetry(apartment, candidate):
    livefit_numbers = normalized_name_numbers(apartment["livefit_name"])
    candidate_numbers = normalized_name_numbers(candidate.get("transaction_apt_name", ""))
    return bool(livefit_numbers) != bool(candidate_numbers)


def has_generic_only_match(apartment, candidate):
    livefit_norm = normalize_name(apartment["livefit_name"])
    candidate_norm = candidate.get("apt_norm", "")
    generic_tokens = (
        "아파트",
        "apt",
        "래미안",
        "자이",
        "푸르지오",
        "힐스테이트",
        "현대",
        "롯데캐슬",
        "아이파크",
        "주공",
        "한신",
        "삼성",
        "대우",
        "벽산",
        "동아",
        "신동아",
        "두산",
    )
    stripped_livefit = livefit_norm
    stripped_candidate = candidate_norm
    for token in generic_tokens:
        stripped_livefit = stripped_livefit.replace(token, "")
        stripped_candidate = stripped_candidate.replace(token, "")
    return len(stripped_livefit) < 3 or len(stripped_candidate) < 3


def rental_suffix_risk(livefit_name, candidate_name):
    livefit = clean_text(livefit_name)
    candidate = clean_text(candidate_name)
    rental_tokens = ("임대", "공공임대", "국민임대", "장기전세")
    return any(token in livefit for token in rental_tokens) != any(token in candidate for token in rental_tokens)


def build_master_name_indexes(apartments):
    by_norm = defaultdict(list)
    by_gu_dong_norm = defaultdict(list)
    for apartment in apartments:
        norm = normalize_name(apartment["livefit_name"])
        if norm:
            by_norm[norm].append(apartment)
            by_gu_dong_norm[(apartment["gu"], normalize_dong(apartment["dong"]), norm)].append(apartment)
    return by_norm, by_gu_dong_norm


def master_match_identity(apartment):
    return (
        apartment.get("livefit_name"),
        apartment.get("kapt_code"),
        apartment.get("road_address"),
    )


def same_master(apartment, other):
    return (
        clean_text(apartment.get("kapt_code"))
        and clean_text(apartment.get("kapt_code")) == clean_text(other.get("kapt_code"))
    ) or normalize_name(apartment.get("livefit_name")) == normalize_name(other.get("livefit_name"))


def lot_matches(apartment, mapping_or_candidate):
    apt_bonbun = normalize_lot_part(apartment.get("bonbun"))
    apt_bubun = normalize_lot_part(apartment.get("bubun"))
    if not apt_bonbun:
        return False
    candidate_jibun = clean_text(mapping_or_candidate.get("transaction_jibun") or mapping_or_candidate.get("jibun_norm"))
    candidate_bonbun = normalize_lot_part(mapping_or_candidate.get("bonbun"))
    candidate_bubun = normalize_lot_part(mapping_or_candidate.get("bubun"))
    if not candidate_bonbun and candidate_jibun:
        candidate_bonbun, candidate_bubun = (candidate_jibun.split("-", 1) + [""])[:2] if "-" in candidate_jibun else (candidate_jibun, "")
        candidate_bonbun = normalize_lot_part(candidate_bonbun)
        candidate_bubun = normalize_lot_part(candidate_bubun)
    return apt_bonbun == candidate_bonbun and apt_bubun == candidate_bubun


def road_address_matches(apartment, mapping_or_candidate):
    livefit_road = normalize_address(apartment.get("road_address"))
    transaction_road = normalize_address(
        mapping_or_candidate.get("transaction_road_address")
        or mapping_or_candidate.get("road_address")
    )
    return bool(livefit_road and transaction_road and livefit_road == transaction_road)


def address_validated(apartment, mapping_or_candidate):
    return road_address_matches(apartment, mapping_or_candidate) or lot_matches(apartment, mapping_or_candidate)


def address_match_value(flag):
    return "Y" if flag else "N"


def match_priority_reason(apartment, mapping_or_candidate, match_type):
    if road_address_matches(apartment, mapping_or_candidate):
        return "ROAD_ADDRESS_EXACT"
    if lot_matches(apartment, mapping_or_candidate):
        return "JIBUN_EXACT"
    if "name" in (match_type or ""):
        return "NAME_ONLY_REVIEW"
    if "alias" in (match_type or "").lower():
        return "ALIAS_REVIEW"
    return "NO_ADDRESS_VALIDATION"


def verified_risk_type(mapping_row, apartment, master_by_norm):
    candidate_name = clean_text(mapping_row.get("transaction_apt_name"))
    if not candidate_name:
        return "VERIFIED_WITHOUT_CANDIDATE", "verified row has no transaction candidate name", "REVIEW"

    try:
        score = float(mapping_row.get("match_confidence") or 0)
    except Exception:
        score = 0
    if road_address_matches(apartment, mapping_row):
        if score >= ROAD_ADDRESS_EXACT_VERIFY_THRESHOLD:
            return (
                "SAFE_ROAD_ADDRESS_EXACT_SCORE",
                "same normalized road address and match_score >= 0.60",
                "KEEP",
            )
        return (
            "MEDIUM_RISK_ROAD_ADDRESS_LOW_NAME_SCORE",
            f"same normalized road address but match_score is below 0.60: score={score:.2f}",
            "DOWNGRADE_OR_REVIEW",
        )

    return (
        "MEDIUM_RISK_WITHOUT_ROAD_ADDRESS_EXACT",
        "verified row is not backed by normalized road address exact match",
        "DOWNGRADE_OR_REVIEW",
    )


def alias_auto_approval_candidate(apartment, by_jibun):
    candidates = same_lot_candidates(apartment, by_jibun)
    if len(candidates) != 1:
        return None, 0, ""

    candidate = candidates[0]
    if normalize_name(apartment["livefit_name"]) == candidate.get("apt_norm", ""):
        return None, 0, "exact_name_uses_deterministic_match"
    score = candidate_similarity(apartment, candidate)
    total_transactions = int(candidate.get("trade_count", 0)) + int(candidate.get("rent_count", 0))
    if score < AUTO_APPROVE_ALIAS_THRESHOLD:
        return None, score, "similarity_below_threshold"
    if total_transactions <= 0:
        return None, score, "no_candidate_transactions"
    if has_number_conflict(apartment, candidate):
        return None, score, "name_number_conflict"
    if has_generic_only_match(apartment, candidate):
        return None, score, "generic_token_only_match"
    if is_dong_prefix_alias(apartment, candidate):
        return None, score, "dong_prefix_alias_requires_address_review"

    return (
        candidate,
        score,
        "same gu/dong/lot unique candidate, high normalized-name similarity, no numeric-token conflict",
    )


def alias_auto_approval_from_mapping_candidate(apartment, mapping_row, by_dong, by_jibun):
    if mapping_row.get("verified") == "Y" or mapping_row.get("match_type") == "unmatched":
        return None, 0, ""
    if mapping_row.get("match_type") != "same_dong_contains_candidate":
        return None, 0, ""
    if len(same_lot_candidates(apartment, by_jibun)) > 1:
        return None, 0, ""

    candidate_name = clean_text(mapping_row.get("transaction_apt_name"))
    candidates = same_dong_candidates(apartment, by_dong)
    candidate = next((item for item in candidates if item.get("transaction_apt_name") == candidate_name), None)
    if not candidate:
        return None, 0, ""

    apartment_bonbun = normalize_lot_part(apartment.get("bonbun"))
    apartment_bubun = normalize_lot_part(apartment.get("bubun"))
    if not apartment_bonbun:
        return None, 0, "address_validation_missing"
    if apartment_bonbun != candidate.get("bonbun") or apartment_bubun != candidate.get("bubun", ""):
        return None, 0, "lot_conflict"

    score = candidate_similarity(apartment, candidate)
    total_transactions = int(candidate.get("trade_count", 0)) + int(candidate.get("rent_count", 0))
    if score < AUTO_APPROVE_ALIAS_THRESHOLD:
        return None, score, "similarity_below_threshold"
    if total_transactions <= 0:
        return None, score, "no_candidate_transactions"
    if has_number_conflict(apartment, candidate):
        return None, score, "name_number_conflict"
    if has_generic_only_match(apartment, candidate):
        return None, score, "generic_token_only_match"
    if is_dong_prefix_alias(apartment, candidate):
        return None, score, "dong_prefix_alias_requires_address_review"

    return (
        candidate,
        score,
        "same gu/dong candidate, high normalized-name similarity, no numeric-token conflict; LiveFit lot key unavailable or compatible",
    )


def same_lot_candidates(apartment, by_jibun):
    bonbun = normalize_lot_part(apartment.get("bonbun"))
    bubun = normalize_lot_part(apartment.get("bubun"))
    if not bonbun:
        return []
    key = (apartment["gu"], normalize_dong(apartment["dong"]), bonbun, bubun)
    return by_jibun.get(key, [])


def same_dong_candidates(apartment, by_dong):
    key = (apartment["gu"], normalize_dong(apartment["dong"]))
    return by_dong.get(key, [])


def best_alias_candidate(apartment, audit, by_dong, by_jibun):
    candidates = same_lot_candidates(apartment, by_jibun) or same_dong_candidates(apartment, by_dong)
    if not candidates:
        return None, 0

    preferred_name = clean_text(audit.get("best_similarity_name")) or clean_text(audit.get("best_candidate_name"))
    best_candidate = None
    best_score = 0
    for candidate in candidates:
        score = candidate_similarity(apartment, candidate)
        if preferred_name and candidate.get("transaction_apt_name") == preferred_name:
            score += 0.03
        if candidate in same_lot_candidates(apartment, by_jibun):
            score += 0.04
        if score > best_score:
            best_score = score
            best_candidate = candidate
    return best_candidate, min(best_score, 1.0)


def build_alias_candidate_report(audit_rows, apartments_by_name, by_dong, by_jibun):
    rows = []
    for audit in audit_rows:
        if audit.get("reason_type") != "NAME_ALIAS":
            continue
        apartment = apartments_by_name.get(audit.get("livefit_name"))
        if not apartment:
            continue
        candidate, score = best_alias_candidate(apartment, audit, by_dong, by_jibun)
        if not candidate:
            continue
        rows.append({
            "livefit_name": apartment["livefit_name"],
            "gu": apartment["gu"],
            "dong": apartment["dong"],
            "kapt_code": apartment["kapt_code"],
            "livefit_normalized_name": normalize_name(apartment["livefit_name"]),
            "transaction_candidate_name": candidate.get("transaction_apt_name", ""),
            "candidate_bonbun": candidate.get("bonbun", ""),
            "candidate_bubun": candidate.get("bubun", ""),
            "candidate_trade_count": candidate.get("trade_count", 0),
            "candidate_rent_count": candidate.get("rent_count", 0),
            "candidate_score": f"{score:.2f}",
            "reason": audit.get("reason_type", ""),
            "recommended_action": "APPROVE_ALIAS_REVIEW" if score >= 0.78 else "MANUAL_REVIEW",
        })

    rows.sort(
        key=lambda row: (
            -float(row["candidate_score"] or 0),
            -(int(row["candidate_trade_count"] or 0) + int(row["candidate_rent_count"] or 0)),
            row["gu"],
            row["dong"],
            row["livefit_name"],
        )
    )
    write_csv(
        ALIAS_CANDIDATES_PATH,
        rows,
        [
            "livefit_name",
            "gu",
            "dong",
            "kapt_code",
            "livefit_normalized_name",
            "transaction_candidate_name",
            "candidate_bonbun",
            "candidate_bubun",
            "candidate_trade_count",
            "candidate_rent_count",
            "candidate_score",
            "reason",
            "recommended_action",
        ],
    )
    return len(rows)


def auto_approve_report_row(apartment, candidate, score, reason):
    return {
        "livefit_name": apartment["livefit_name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "kapt_code": apartment["kapt_code"],
        "livefit_normalized_name": normalize_name(apartment["livefit_name"]),
        "transaction_candidate_name": candidate.get("transaction_apt_name", ""),
        "candidate_bonbun": candidate.get("bonbun", ""),
        "candidate_bubun": candidate.get("bubun", ""),
        "candidate_trade_count": candidate.get("trade_count", 0),
        "candidate_rent_count": candidate.get("rent_count", 0),
        "candidate_score": f"{score:.2f}",
        "match_type": "AUTO_APPROVE_ALIAS",
        "auto_approved": "Y",
        "approval_reason": reason,
        "approved_at": date.today().isoformat(),
    }


def write_auto_approve_alias_report(rows):
    rows.sort(
        key=lambda row: (
            -float(row["candidate_score"] or 0),
            row["gu"],
            row["dong"],
            row["livefit_name"],
        )
    )
    write_csv(
        AUTO_APPROVE_ALIAS_PATH,
        rows,
        [
            "livefit_name",
            "gu",
            "dong",
            "kapt_code",
            "livefit_normalized_name",
            "transaction_candidate_name",
            "candidate_bonbun",
            "candidate_bubun",
            "candidate_trade_count",
            "candidate_rent_count",
            "candidate_score",
            "match_type",
            "auto_approved",
            "approval_reason",
            "approved_at",
        ],
    )
    return len(rows)


def build_quick_review_report(audit_rows, apartments_by_name, by_dong, by_jibun):
    rows = []
    for audit in audit_rows:
        if audit.get("reason_type") != "NAME_ALIAS":
            continue
        apartment = apartments_by_name.get(audit.get("livefit_name"))
        if not apartment:
            continue
        if len(same_lot_candidates(apartment, by_jibun)) > 1:
            continue
        candidate, _ = best_alias_candidate(apartment, audit, by_dong, by_jibun)
        if not candidate:
            continue
        score = candidate_similarity(apartment, candidate)
        if not (QUICK_REVIEW_MIN_SCORE <= score < QUICK_REVIEW_MAX_SCORE):
            continue
        action = "REVIEW_APPROVE"
        if (
            has_number_conflict(apartment, candidate)
            or has_number_asymmetry(apartment, candidate)
            or has_generic_only_match(apartment, candidate)
        ):
            action = "REVIEW_REJECT"
        rows.append({
            "livefit_name": apartment["livefit_name"],
            "transaction_candidate_name": candidate.get("transaction_apt_name", ""),
            "candidate_score": f"{score:.2f}",
            "gu": apartment["gu"],
            "dong": apartment["dong"],
            "bonbun": candidate.get("bonbun", ""),
            "bubun": candidate.get("bubun", ""),
            "candidate_trade_count": candidate.get("trade_count", 0),
            "candidate_rent_count": candidate.get("rent_count", 0),
            "recommended_action": action,
        })
    rows.sort(
        key=lambda row: (
            row["recommended_action"],
            -float(row["candidate_score"] or 0),
            -(int(row["candidate_trade_count"] or 0) + int(row["candidate_rent_count"] or 0)),
            row["gu"],
            row["dong"],
            row["livefit_name"],
        )
    )
    write_csv(
        QUICK_REVIEW_PATH,
        rows,
        [
            "livefit_name",
            "transaction_candidate_name",
            "candidate_score",
            "gu",
            "dong",
            "bonbun",
            "bubun",
            "candidate_trade_count",
            "candidate_rent_count",
            "recommended_action",
        ],
    )
    return len(rows)


def build_same_lot_review_report(audit_rows, apartments_by_name, by_jibun):
    rows = []
    for audit in audit_rows:
        if audit.get("reason_type") != "SAME_LOT_MULTIPLE_COMPLEX":
            continue
        apartment = apartments_by_name.get(audit.get("livefit_name"))
        if not apartment:
            continue
        candidates = same_lot_candidates(apartment, by_jibun)
        names = []
        trade_counts = []
        rent_counts = []
        scores = []
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                -candidate_similarity(apartment, item),
                -(int(item.get("trade_count", 0)) + int(item.get("rent_count", 0))),
                item.get("transaction_apt_name", ""),
            )
        )
        for candidate in sorted_candidates:
            names.append(candidate.get("transaction_apt_name", ""))
            trade_counts.append(str(candidate.get("trade_count", 0)))
            rent_counts.append(str(candidate.get("rent_count", 0)))
            scores.append(f"{candidate_similarity(apartment, candidate):.2f}")
        rows.append({
            "livefit_name": apartment["livefit_name"],
            "gu": apartment["gu"],
            "dong": apartment["dong"],
            "bonbun": normalize_lot_part(apartment.get("bonbun")),
            "bubun": normalize_lot_part(apartment.get("bubun")),
            "candidate_transaction_names": "|".join(names),
            "candidate_count": len(candidates),
            "candidate_trade_counts": "|".join(trade_counts),
            "candidate_rent_counts": "|".join(rent_counts),
            "candidate_scores": "|".join(scores),
            "risk_reason": "MULTIPLE_COMPLEX_REQUIRES_REVIEW",
            "recommended_action": "MANUAL_REVIEW",
        })
    write_csv(
        SAME_LOT_REVIEW_PATH,
        rows,
        [
            "livefit_name",
            "gu",
            "dong",
            "bonbun",
            "bubun",
            "candidate_transaction_names",
            "candidate_count",
            "candidate_trade_counts",
            "candidate_rent_counts",
            "candidate_scores",
            "risk_reason",
            "recommended_action",
        ],
    )
    return len(rows)


def missing_bonbun_reason(apartment):
    if not clean_text(apartment.get("jibun")):
        return "DETAIL_ADDRESS_EMPTY"
    if not normalize_lot_part(apartment.get("bonbun")):
        return "KAPT_ADDRESS_UNPARSEABLE"
    return "MULTIPLE_ADDRESS_PATTERNS"


def build_missing_bonbun_report(audit_rows, apartments_by_name):
    rows = []
    for audit in audit_rows:
        if audit.get("reason_type") != "MISSING_BONBUN_BUBUN":
            continue
        apartment = apartments_by_name.get(audit.get("livefit_name"))
        if not apartment:
            continue
        rows.append({
            "livefit_name": apartment["livefit_name"],
            "gu": apartment["gu"],
            "dong": apartment["dong"],
            "kapt_code": apartment["kapt_code"],
            "kapt_road_address": apartment["road_address"],
            "detail_address": apartment.get("jibun", ""),
            "parsed_bonbun": normalize_lot_part(apartment.get("bonbun")),
            "parsed_bubun": normalize_lot_part(apartment.get("bubun")),
            "missing_reason": missing_bonbun_reason(apartment),
            "possible_source": "K-apt master address cleanup",
        })
    write_csv(
        MISSING_BONBUN_ANALYSIS_PATH,
        rows,
        [
            "livefit_name",
            "gu",
            "dong",
            "kapt_code",
            "kapt_road_address",
            "detail_address",
            "parsed_bonbun",
            "parsed_bubun",
            "missing_reason",
            "possible_source",
        ],
    )
    return len(rows)


def classify_reverse_match(apartment, mapping_row, master_by_norm, by_dong, by_jibun):
    candidate_name = clean_text(mapping_row.get("transaction_apt_name"))
    if not candidate_name:
        return "NO_MASTER_MATCH", None, "NO_CANDIDATE", "no transaction candidate name"

    candidate_norm = normalize_name(candidate_name)
    exact_master_matches = master_by_norm.get(candidate_norm, [])
    other_exact = [item for item in exact_master_matches if not same_master(apartment, item)]
    if len(other_exact) == 1:
        matched = other_exact[0]
        if address_validated(apartment, mapping_row):
            return (
                "REBUILD_RENAME_CANDIDATE",
                matched,
                "MANUAL_REVIEW_REBUILD_RENAME",
                "transaction name exists as another current master, but address/lot matches this LiveFit master; likely rebuild or rename lineage",
            )
        return (
            "CANDIDATE_EXISTS_IN_MASTER",
            matched,
            "REJECT_FOR_CURRENT_AND_ASSIGN_TO_EXISTING_MASTER",
            "transaction candidate name is an exact LiveFit master name",
        )
    if len(other_exact) > 1:
        return (
            "AMBIGUOUS_MASTER_MATCH",
            other_exact[0],
            "MANUAL_REVIEW",
            "transaction candidate name maps to multiple LiveFit masters",
        )

    livefit_core = strip_dong_prefix(apartment["livefit_name"], apartment["dong"])
    if livefit_core and livefit_core == candidate_norm and normalize_name(apartment["livefit_name"]) != candidate_norm:
        same_lot = len(same_lot_candidates(apartment, by_jibun))
        action = "ADDRESS_VALIDATION_REQUIRED"
        notes = "dong-prefix alias; do not auto-approve without road/lot validation"
        if same_lot == 1 and lot_matches(apartment, same_lot_candidates(apartment, by_jibun)[0]):
            action = "REVIEW_ADDRESS_VALIDATED_ALIAS"
            notes = "dong-prefix alias with same lot candidate; still review for nearby same-brand complexes"
        return "DONG_PREFIX_ALIAS", None, action, notes

    candidates = same_dong_candidates(apartment, by_dong)
    related_master_count = 0
    for other in candidates:
        other_norm = other.get("apt_norm", "")
        if other_norm == candidate_norm:
            related_master_count += 1
    if related_master_count > 1:
        return "AMBIGUOUS_MASTER_MATCH", None, "MANUAL_REVIEW", "multiple same-dong transaction candidates share this raw name"

    synthetic_candidate = {"transaction_apt_name": candidate_name}
    score = SequenceMatcher(None, normalize_name(apartment["livefit_name"]), candidate_norm).ratio()
    if score >= 0.86 and not has_number_conflict(apartment, synthetic_candidate) and not has_generic_only_match(apartment, synthetic_candidate):
        return "GENERIC_ALIAS", None, "REVIEW_APPROVE_IF_ADDRESS_OK", "likely suffix/spacing/brand alias, address validation still preferred"

    if exact_master_matches:
        return "AMBIGUOUS_MASTER_MATCH", exact_master_matches[0], "MANUAL_REVIEW", "candidate overlaps master naming but identity is unclear"

    return "NO_MASTER_MATCH", None, "MANUAL_REVIEW", "raw name does not directly exist in LiveFit master"


def mapping_apartment_lookup(mapping_row, apartments_by_name, apartments_by_key):
    key = (
        clean_text(mapping_row.get("livefit_name")),
        clean_text(mapping_row.get("kapt_code")),
    )
    if apartments_by_key and key in apartments_by_key:
        return apartments_by_key[key]
    return apartments_by_name.get(clean_text(mapping_row.get("livefit_name")))


def build_verified_audit_report(mapping_rows, apartments_by_name, master_by_norm, apartments_by_key=None):
    rows = []
    for mapping_row in mapping_rows:
        if clean_text(mapping_row.get("verified")).upper() != "Y" and "risk_review" not in mapping_row.get("match_type", ""):
            continue
        apartment = mapping_apartment_lookup(mapping_row, apartments_by_name, apartments_by_key)
        if not apartment:
            continue
        risk_type, detail, action = verified_risk_type(mapping_row, apartment, master_by_norm)
        if "risk_review" in mapping_row.get("match_type", ""):
            action = "DOWNGRADED_FROM_VERIFIED"
        rows.append({
            "livefit_name": mapping_row.get("livefit_name"),
            "gu": mapping_row.get("gu"),
            "dong": mapping_row.get("dong"),
            "kapt_code": mapping_row.get("kapt_code"),
            "transaction_candidate_name": mapping_row.get("transaction_apt_name"),
            "transaction_jibun": mapping_row.get("transaction_jibun"),
            "match_type": mapping_row.get("match_type"),
            "match_confidence": mapping_row.get("match_confidence"),
            "verified": mapping_row.get("verified"),
            "risk_type": risk_type,
            "risk_detail": detail,
            "recommended_action": action,
        })
    rows.sort(key=lambda row: (row["risk_type"], row["gu"], row["dong"], row["livefit_name"]))
    write_csv(
        VERIFIED_AUDIT_PATH,
        rows,
        [
            "livefit_name",
            "gu",
            "dong",
            "kapt_code",
            "transaction_candidate_name",
            "transaction_jibun",
            "match_type",
            "match_confidence",
            "verified",
            "risk_type",
            "risk_detail",
            "recommended_action",
        ],
    )

    risk_counts = Counter(row["risk_type"] for row in rows)
    summary_rows = [
        {"risk_type": risk, "count": count}
        for risk, count in risk_counts.most_common()
    ]
    write_csv(VERIFIED_RISK_SUMMARY_PATH, summary_rows, ["risk_type", "count"])
    return len(rows), risk_counts


def build_raw_name_reverse_audit(audit_rows, apartments_by_name, master_by_norm, by_dong, by_jibun):
    rows = []
    for audit in audit_rows:
        if audit.get("current_match_status") not in {"candidate", "unmatched"}:
            continue
        apartment = apartments_by_name.get(audit.get("livefit_name"))
        if not apartment:
            continue
        candidate_name = clean_text(audit.get("best_candidate_name"))
        candidate = None
        for item in same_lot_candidates(apartment, by_jibun) or same_dong_candidates(apartment, by_dong):
            if clean_text(item.get("transaction_apt_name")) == candidate_name:
                candidate = item
                break
        mapping_like = {
            "transaction_apt_name": candidate_name,
            "transaction_road_address": candidate.get("transaction_road_address", "") if candidate else clean_text(audit.get("transaction_road_address")),
            "transaction_jibun": candidate.get("transaction_jibun", "") if candidate else clean_text(audit.get("best_candidate_jibun")),
            "bonbun": candidate.get("bonbun", "") if candidate else clean_text(audit.get("transaction_bonbun")),
            "bubun": candidate.get("bubun", "") if candidate else clean_text(audit.get("transaction_bubun")),
        }
        reverse_type, matched_master, action, notes = classify_reverse_match(
            apartment,
            mapping_like,
            master_by_norm,
            by_dong,
            by_jibun,
        )
        rows.append({
            "livefit_name": apartment["livefit_name"],
            "transaction_candidate_name": candidate_name,
            "gu": apartment["gu"],
            "dong": apartment["dong"],
            "livefit_road_address": apartment.get("road_address", ""),
            "transaction_road_address": mapping_like.get("transaction_road_address", ""),
            "livefit_bonbun": normalize_lot_part(apartment.get("bonbun")),
            "livefit_bubun": normalize_lot_part(apartment.get("bubun")),
            "bonbun": candidate.get("bonbun", "") if candidate else normalize_lot_part(apartment.get("bonbun")),
            "bubun": candidate.get("bubun", "") if candidate else normalize_lot_part(apartment.get("bubun")),
            "transaction_bonbun": mapping_like.get("bonbun", ""),
            "transaction_bubun": mapping_like.get("bubun", ""),
            "road_address_match": address_match_value(road_address_matches(apartment, mapping_like)),
            "jibun_match": address_match_value(lot_matches(apartment, mapping_like)),
            "match_priority_reason": match_priority_reason(apartment, mapping_like, audit.get("current_match_status", "")),
            "road_name": apartment.get("road_name", ""),
            "road_address": apartment.get("road_address", ""),
            "candidate_score": audit.get("best_candidate_score", ""),
            "candidate_trade_count": candidate.get("trade_count", "") if candidate else "",
            "candidate_rent_count": candidate.get("rent_count", "") if candidate else "",
            "reverse_match_type": reverse_type,
            "matched_master_name": matched_master.get("livefit_name", "") if matched_master else "",
            "matched_master_kapt_code": matched_master.get("kapt_code", "") if matched_master else "",
            "matched_master_road_address": matched_master.get("road_address", "") if matched_master else "",
            "recommended_action": action,
            "notes": notes,
        })
    rows.sort(key=lambda row: (row["reverse_match_type"], row["gu"], row["dong"], row["livefit_name"]))
    write_csv(
        RAW_NAME_REVERSE_AUDIT_PATH,
        rows,
        [
            "livefit_name",
            "transaction_candidate_name",
            "gu",
            "dong",
            "livefit_road_address",
            "transaction_road_address",
            "livefit_bonbun",
            "livefit_bubun",
            "bonbun",
            "bubun",
            "transaction_bonbun",
            "transaction_bubun",
            "road_address_match",
            "jibun_match",
            "match_priority_reason",
            "road_name",
            "road_address",
            "candidate_score",
            "candidate_trade_count",
            "candidate_rent_count",
            "reverse_match_type",
            "matched_master_name",
            "matched_master_kapt_code",
            "matched_master_road_address",
            "recommended_action",
            "notes",
        ],
    )
    build_manual_review_batch(rows)
    return len(rows), Counter(row["reverse_match_type"] for row in rows)


def build_manual_review_batch(reverse_rows):
    target_types = {"CANDIDATE_EXISTS_IN_MASTER", "DONG_PREFIX_ALIAS", "REBUILD_RENAME_CANDIDATE"}
    selected = [row for row in reverse_rows if row.get("reverse_match_type") in target_types]
    priority = {
        "REBUILD_RENAME_CANDIDATE": 0,
        "CANDIDATE_EXISTS_IN_MASTER": 1,
        "DONG_PREFIX_ALIAS": 2,
    }

    def to_float(value):
        try:
            return float(clean_text(value) or 0)
        except Exception:
            return 0.0

    def to_int(value):
        try:
            return int(float(clean_text(value) or 0))
        except Exception:
            return 0

    selected.sort(key=lambda row: (
        priority.get(row.get("reverse_match_type"), 99),
        -to_float(row.get("candidate_score")),
        -(to_int(row.get("candidate_trade_count")) + to_int(row.get("candidate_rent_count"))),
        row.get("gu", ""),
        row.get("dong", ""),
        row.get("livefit_name", ""),
    ))
    fields = [
        "livefit_name",
        "transaction_candidate_name",
        "reverse_match_type",
        "gu",
        "dong",
        "livefit_road_address",
        "transaction_road_address",
        "livefit_bonbun",
        "livefit_bubun",
        "transaction_bonbun",
        "transaction_bubun",
        "road_address_match",
        "jibun_match",
        "match_priority_reason",
        "bonbun",
        "bubun",
        "matched_master_name",
        "matched_master_road_address",
        "candidate_trade_count",
        "candidate_rent_count",
        "candidate_score",
        "recommended_action",
        "review_decision",
        "review_notes",
    ]
    output_rows = []
    for row in selected:
        item = {field: row.get(field, "") for field in fields}
        item["review_decision"] = ""
        item["review_notes"] = ""
        output_rows.append(item)
    write_csv(MANUAL_REVIEW_BATCH_PATH, output_rows, fields)
    # write_csv already uses utf-8-sig, so this companion file is Excel-friendly too.
    write_csv(MANUAL_REVIEW_BATCH_EXCEL_PATH, output_rows, fields)
    return len(output_rows)


def build_mapping():
    ensure_transaction_dirs()
    apartments = read_apartment_master()
    apartments_by_name = {apartment["livefit_name"]: apartment for apartment in apartments}
    apartments_by_key = {
        (clean_text(apartment["livefit_name"]), clean_text(apartment["kapt_code"])): apartment
        for apartment in apartments
    }
    master_by_norm, master_by_gu_dong_norm = build_master_name_indexes(apartments)
    candidates = load_transaction_candidates()
    manual_overrides = load_manual_overrides()
    rejected_pairs = load_reject_overrides()
    by_road, by_name, by_dong, by_jibun, by_road_number = build_indexes(candidates)

    rows = []
    audit_rows = []
    auto_approve_rows = []
    matched = 0
    verified = 0
    for apartment in apartments:
        override = manual_overrides.get(apartment["livefit_name"])
        if override:
            row = manual_mapping_row(apartment, override)
        else:
            auto_candidate, auto_score, auto_reason = alias_auto_approval_candidate(apartment, by_jibun)
            if auto_candidate and is_rejected_candidate(apartment, auto_candidate, rejected_pairs):
                row = reject_excluded_row(apartment, auto_candidate)
            elif auto_candidate:
                row = auto_approve_mapping_row(apartment, auto_candidate, auto_score, auto_reason)
                auto_approve_rows.append(auto_approve_report_row(apartment, auto_candidate, auto_score, auto_reason))
            else:
                row = match_apartment(apartment, by_road, by_name, by_dong, by_jibun, by_road_number)
                if row.get("transaction_apt_name") and (
                    apartment["livefit_name"],
                    normalize_name(row.get("transaction_apt_name")),
                ) in rejected_pairs:
                    row = reject_excluded_row(apartment, {
                        "transaction_apt_name": row.get("transaction_apt_name", ""),
                        "transaction_road_address": row.get("transaction_road_address", ""),
                        "transaction_jibun": row.get("transaction_jibun", ""),
                    })
                alias_candidate, alias_score, alias_reason = alias_auto_approval_from_mapping_candidate(
                    apartment,
                    row,
                    by_dong,
                    by_jibun,
                )
                if alias_candidate and is_rejected_candidate(apartment, alias_candidate, rejected_pairs):
                    row = reject_excluded_row(apartment, alias_candidate)
                elif alias_candidate:
                    row = auto_approve_mapping_row(apartment, alias_candidate, alias_score, alias_reason)
                    auto_approve_rows.append(auto_approve_report_row(apartment, alias_candidate, alias_score, alias_reason))
        if row.get("verified") == "Y" and row.get("manual_override") != "Y":
            risk_type, risk_detail, _ = verified_risk_type(row, apartment, master_by_norm)
            if risk_type in {
                "HIGH_RISK_WRONG_MASTER_MATCH",
                "HIGH_RISK_NUMBER_MISMATCH",
                "MEDIUM_RISK_NAME_WITHOUT_ADDRESS_VALIDATION",
                "MEDIUM_RISK_ROAD_ADDRESS_LOW_NAME_SCORE",
                "MEDIUM_RISK_WITHOUT_ROAD_ADDRESS_EXACT",
            }:
                row["verified"] = "N"
                row["match_type"] = f"{row.get('match_type')}_risk_review"
                row["match_confidence"] = min(float(row.get("match_confidence") or 0), 0.60)
                row["notes"] = f"auto-downgraded from verified: {risk_type}; {risk_detail}"
        rows.append(row)
        audit_rows.append(audit_row(row, apartment, by_dong, by_jibun))
        if row["match_type"] != "unmatched":
            matched += 1
        if row["verified"] == "Y":
            verified += 1

    write_csv(TRANSACTION_MAPPING_PATH, rows, MAPPING_FIELDS)
    write_csv(
        TRANSACTION_MAPPING_AUDIT_PATH,
        audit_rows,
        [
            "livefit_name",
            "gu",
            "dong",
            "road_address",
            "livefit_road_address",
            "transaction_road_address",
            "livefit_bonbun",
            "livefit_bubun",
            "transaction_bonbun",
            "transaction_bubun",
            "road_address_match",
            "jibun_match",
            "match_priority_reason",
            "kapt_code",
            "kapt_name",
            "current_match_status",
            "best_candidate_name",
            "best_candidate_road_address",
            "best_candidate_score",
            "candidate_names",
            "candidate_count",
            "reason_type",
            "reason_detail",
            "resolution_bucket",
            "best_name_similarity",
            "best_similarity_name",
            "recommended_action",
            "notes",
        ],
    )
    reason_summary_rows = []
    reason_counts = Counter(row["reason_type"] for row in audit_rows if row["reason_type"] != "MATCHED")
    status_reason_counts = Counter(
        (row["current_match_status"], row["reason_type"])
        for row in audit_rows
        if row["reason_type"] != "MATCHED"
    )
    for reason, count in reason_counts.most_common():
        reason_summary_rows.append({
            "reason_type": reason,
            "count": count,
            "candidate_count": status_reason_counts.get(("candidate", reason), 0),
            "unmatched_count": status_reason_counts.get(("unmatched", reason), 0),
        })
    reason_summary_path = TRANSACTION_MAPPING_AUDIT_PATH.with_name("transaction_mapping_reason_summary.csv")
    write_csv(
        reason_summary_path,
        reason_summary_rows,
        ["reason_type", "count", "candidate_count", "unmatched_count"],
    )
    alias_count = build_alias_candidate_report(audit_rows, apartments_by_name, by_dong, by_jibun)
    quick_review_count = build_quick_review_report(audit_rows, apartments_by_name, by_dong, by_jibun)
    auto_approve_count = write_auto_approve_alias_report(auto_approve_rows)
    same_lot_count = build_same_lot_review_report(audit_rows, apartments_by_name, by_jibun)
    missing_bonbun_count = build_missing_bonbun_report(audit_rows, apartments_by_name)
    verified_audit_count, verified_risk_counts = build_verified_audit_report(
        rows,
        apartments_by_name,
        master_by_norm,
        apartments_by_key,
    )
    reverse_audit_count, reverse_counts = build_raw_name_reverse_audit(
        audit_rows,
        apartments_by_name,
        master_by_norm,
        by_dong,
        by_jibun,
    )
    print(f"[OK] apartment_transaction_mapping.csv rows={len(rows)} path={TRANSACTION_MAPPING_PATH}")
    print(f"[OK] matched_or_candidate={matched} verified={verified} unmatched={len(rows) - matched}")
    print(f"[OK] transaction_mapping_audit.csv rows={len(audit_rows)} path={TRANSACTION_MAPPING_AUDIT_PATH}")
    print(f"[OK] transaction_mapping_reason_summary.csv rows={len(reason_summary_rows)} path={reason_summary_path}")
    print(f"[OK] transaction_auto_approve_alias.csv rows={auto_approve_count} path={AUTO_APPROVE_ALIAS_PATH}")
    print(f"[OK] transaction_alias_candidates.csv rows={alias_count} path={ALIAS_CANDIDATES_PATH}")
    print(f"[OK] transaction_quick_review.csv rows={quick_review_count} path={QUICK_REVIEW_PATH}")
    print(f"[OK] transaction_same_lot_review.csv rows={same_lot_count} path={SAME_LOT_REVIEW_PATH}")
    print(f"[OK] missing_bonbun_bubun_analysis.csv rows={missing_bonbun_count} path={MISSING_BONBUN_ANALYSIS_PATH}")
    print(f"[OK] transaction_verified_mapping_audit.csv rows={verified_audit_count} path={VERIFIED_AUDIT_PATH}")
    print(f"[OK] transaction_verified_risk_summary.csv rows={len(verified_risk_counts)} path={VERIFIED_RISK_SUMMARY_PATH}")
    print(f"[OK] transaction_raw_name_reverse_audit.csv rows={reverse_audit_count} path={RAW_NAME_REVERSE_AUDIT_PATH}")
    if reason_counts:
        print("[OK] failure reason counts:")
        for reason, count in reason_counts.most_common():
            print(f"  - {reason}: {count}")
    if not candidates:
        print("[WARNING] transaction_master.csv has no transaction candidates yet.")


if __name__ == "__main__":
    build_mapping()
