# rag_agent/ingest/fetch_and_parse.py
import httpx, hashlib, json, unicodedata, io, re
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
BRONZE_DIR = ROOT / "data" / "bronze"
URLS_PATH = ROOT / "rag_agent" / "ingest" / "urls.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "credit-risk-rag-bot/0.1 (+github.com/janghjun/finance-credit-risk-mlops)"
}

MAIN_SELECTORS = [
    "article",
    "#content",
    ".boardView",
    ".bd_view",
    ".view_cont",
    ".article",
    ".post",
    ".content",
    ".contents",
    ".view",
    "#contents",
]


def _is_valid_url(u: str) -> bool:
    try:
        pu = urlparse(u.strip())
        return bool(pu.scheme in ("http", "https") and pu.netloc)
    except Exception:
        return False


def main():
    urls = json.load(open(URLS_PATH, encoding="utf-8"))

    if not isinstance(urls, list):
        print("❌ urls.json이 리스트 형태가 아닙니다:", type(urls))
        return
    if not urls:
        print("❌ urls.json이 비어 있습니다. crawl_sources.py를 먼저 실행하세요.")
        return

    for url in urls:
        if not (isinstance(url, str) and _is_valid_url(url)):
            print("⚠️ skip invalid url:", repr(url))
            continue


def normalize_text(txt: str) -> str:
    txt = unicodedata.normalize("NFKC", txt)
    # 공백 압축
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def extract_main_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for s in soup(["script", "style", "noscript"]):
        s.extract()

    # 우선 본문 후보 컨테이너에서 텍스트 추출
    for sel in MAIN_SELECTORS:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(" ", strip=True)

    # fallback: 전체에서 텍스트
    return soup.get_text(" ", strip=True)


def extract_pdf_text_from_bytes(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


def fetch(url: str) -> httpx.Response:
    r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r


def find_pdf_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            # 절대/상대 링크 처리
            if href.startswith("http"):
                links.append(href)
            else:
                # 간단한 상대경로 처리
                if base_url.endswith("/") and href.startswith("/"):
                    links.append(base_url.rstrip("/") + href)
                elif base_url.endswith("/") or href.startswith("/"):
                    # 적당히 붙이기
                    from urllib.parse import urljoin

                    links.append(urljoin(base_url, href))
                else:
                    links.append(f"{base_url.rstrip('/')}/{href.lstrip('/')}")
    return list(dict.fromkeys(links))  # 중복 제거 유지 순서


def main():
    urls = json.load(open(URLS_PATH, encoding="utf-8"))
    for url in urls:
        try:
            r = fetch(url)
        except Exception as e:
            print("❌ fail", url, e)
            continue

        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        raw_path = RAW_DIR / f"{h}.json"
        bronze_path = BRONZE_DIR / f"{h}.json"

        content_type = (r.headers.get("Content-Type") or "").lower()
        text_all = ""

        if "html" in content_type or url.lower().endswith((".html", ".htm")):
            html_text = extract_main_html_text(r.text)
            text_all += html_text

            # 첨부 PDF 찾아서 텍스트 합치기
            pdf_links = find_pdf_links(r.text, url)
            for plink in pdf_links[:3]:  # 폭주 방지: 최대 3개
                try:
                    pr = fetch(plink)
                    if (
                        b"%PDF" in pr.content[:1024]
                        or "pdf" in (pr.headers.get("content-type") or "").lower()
                    ):
                        text_all += "\n" + extract_pdf_text_from_bytes(pr.content)
                except Exception as e:
                    print("⚠️ pdf fetch fail", plink, e)

        elif "pdf" in content_type or url.lower().endswith(".pdf"):
            text_all = extract_pdf_text_from_bytes(r.content)

        else:
            # 기타는 우선 텍스트로 시도
            try:
                text_all = r.text
            except Exception:
                text_all = ""

        text_all = normalize_text(text_all)

        raw_doc = {
            "doc_id": h,
            "url": url,
            "status": r.status_code,
            "content_type": content_type,
            "has_pdf_attachments": "true" if "pdf" in content_type else "false",
            "text_head": text_all[:1000],  # 스니펫만 보관
        }
        raw_path.write_text(json.dumps(raw_doc, ensure_ascii=False), encoding="utf-8")

        bronze_doc = {
            "doc_id": h,
            "url": url,
            "text_norm": text_all,
            "char_len": len(text_all),
            "low_quality": len(text_all) < 300,
        }
        bronze_path.write_text(
            json.dumps(bronze_doc, ensure_ascii=False), encoding="utf-8"
        )

        print(f"✅ saved {url} (chars={len(text_all)})")


if __name__ == "__main__":
    main()
