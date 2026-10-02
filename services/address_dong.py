"""주소에서 서울 자치구와 법정동 이름을 읽는다(2026-10-02).

예전에는 괄호 안에서 '동/가'로 끝나는 첫 단어를 동으로 읽어, 건물 이름("미도상가",
"청실상가동", "주상가동")이나 건물 동 번호("1202동")를 동으로 잘못 셌다. 구는 학원 데이터의
'행정구역명'을 썼는데, 실제 주소의 구와 다른 학원(43곳)과 비어 있는 학원(46곳)이 있었다.

법정동 전체 목록이 없어(아파트가 있는 동 343개만 보유) 이름 형태로 판별한다:
'○○동' 또는 '○○N가'이고, 숫자로 시작하지 않으며, 건물을 뜻하는 단어가 없는 첫 단어.
"""
import re

BUILDING_WORDS = (
    "상가", "빌딩", "타워", "센터", "시장", "아파트", "오피스텔", "플라자", "프라자", "쇼핑",
    "스퀘어", "캐슬", "팰리스", "하이츠", "빌라", "맨션", "회관", "몰", "프라임", "오피스",
)
DONG_NAME = re.compile(r"^[가-힣]+(?:[0-9]*동|[0-9]+가)$")
GU_NAME = re.compile(r"서울(?:특별시)?\s+([가-힣]+구)(?:\s|$)")


def _top_level_groups(text):
    """괄호 짝을 맞춰 가장 바깥 괄호 안의 내용만. '(연희동,(주)희훈)'도 한 덩어리로 읽는다."""
    groups, depth, buf = [], 0, []
    for ch in text or "":
        if ch == "(":
            if depth:
                buf.append(ch)
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth:
                buf.append(ch)
            else:
                groups.append("".join(buf))
                buf = []
        elif depth:
            buf.append(ch)
    return groups


def legal_dong_from_address(address):
    """괄호 안 '(법정동, 건물명)'에서 법정동만. 뒤쪽 괄호부터 보고 못 찾으면 빈 문자열.
    '진관동102'·'신당동 340-73'처럼 뒤에 붙은 번지는 떼고 판별한다."""
    for group in reversed(_top_level_groups(address)):
        for token in group.split(","):
            words = token.strip().split()
            if not words:
                continue
            name = re.sub(r"[0-9-]+$", "", words[0]) if not re.search(r"[0-9]+가$", words[0]) else words[0]
            if DONG_NAME.match(name) and not any(word in name for word in BUILDING_WORDS):
                return name
    return ""


def gu_from_address(address):
    """'서울특별시 강남구 …'에서 자치구. 없으면 빈 문자열."""
    match = GU_NAME.search(address or "")
    return match.group(1) if match else ""
