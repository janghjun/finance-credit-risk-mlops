import json
from pathlib import Path
from urllib.parse import urlparse
import yaml

ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = ROOT / "rag_agent" / "ingest" / "sources.yaml"
OUT_PATH = ROOT / "rag_agent" / "ingest" / "urls.json"


def _is_valid_url(u: str) -> bool:
    try:
        pu = urlparse(u.strip())
        return bool(pu.scheme in ("http", "https") and pu.netloc)
    except Exception:
        return False


def main():
    cfg = yaml.safe_load(open(YAML_PATH, encoding="utf-8"))
    raw_urls = []
    for src in cfg.get("sources", []):
        t = src.get("type")
        if t == "list":
            raw_urls.extend(src.get("urls", []))
        # rss/sitemap는 추후 확장

    # 1) 문자열만, 공백 제거
    urls = [u.strip() for u in raw_urls if isinstance(u, str)]
    # 2) 빈 값 제거
    urls = [u for u in urls if u]
    # 3) 유효한 URL만
    valid = [u for u in urls if _is_valid_url(u)]
    # 4) 중복 제거
    uniq = sorted(set(valid))

    # 검증 로그
    print(
        f"[crawl] total={len(raw_urls)} stripped={len(urls)} valid={len(valid)} unique={len(uniq)}"
    )
    bad = set(urls) - set(valid)
    if bad:
        print("[crawl] filtered INVALID urls:")
        for b in sorted(bad):
            print(" -", b)

    json.dump(uniq, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[crawl] wrote {len(uniq)} urls -> {OUT_PATH}")


if __name__ == "__main__":
    main()
