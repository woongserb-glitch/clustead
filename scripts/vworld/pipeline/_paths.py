"""v5 동 건물 매칭 파이프라인 공통 경로·키.

REPO  저장소 루트(Path) / R 같은 경로의 문자열(슬래시) / V 산출물 폴더(data/derived/vworld, 문자열)
ENV   환경변수 위에 .env 를 겹친 dict(값은 출력하지 않는다). .env 는 저장소 루트 →
      (워크트리에 없으면) data 폴더가 가리키는 원래 폴더 순으로 찾는다.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
R = str(REPO).replace("\\", "/")
V = f"{R}/data/derived/vworld"
os.makedirs(V, exist_ok=True)


def _load_env():
    from dotenv import dotenv_values

    env = {}
    candidates = [REPO / ".env"]
    data_dir = REPO / "data"
    try:
        # 워크트리의 data 는 원래 폴더 data 로 연결(junction)돼 있다 — 그 옆 .env
        candidates.append(Path(os.path.realpath(data_dir)).parent / ".env")
    except OSError:
        pass
    for path in candidates:
        if path.exists():
            env.update({k: v for k, v in dotenv_values(path).items() if v})
            break
    env.update({k: v for k, v in os.environ.items() if k in (
        "KAKAO_REST_API_KEY", "VWORLD_API_KEY", "V-WORLD_KEY") and v})
    return env


ENV = _load_env()
