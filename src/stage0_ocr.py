"""Stage 0 (TCM/PDF sources): OCR a page range of a scanned PDF into raw per-page text.

The three TCM source books under data/raw/TCM/ are scanned images (no text layer --
verified with pdfplumber: extract_text() returns "" on every sampled page, each page
carries exactly one full-page DCTDecode/JPEG image). This stage extracts each page's
embedded JPEG directly (no re-rendering needed) and OCRs it locally.

Engine choice: macOS Vision framework (VNRecognizeTextRequest, accurate mode, zh-Hans),
not an LLM. Two alternatives were benchmarked on the same sample page against a careful
manual transcription:
  - gpt-5.2 vision (LLM OCR): fluent but ~5-8 confident-looking *wrong* substitutions per
    page (e.g. "少腹逐瘀汤" -> "少腹逐六汤", "耻骨毛际" -> "脐胃毛际") -- semantically
    plausible, hard to catch, and not viable to run over several thousand pages anyway
    (~40s/page, per-page API cost).
  - Tesseract (chi_sim): more character-level garbling than either.
  - macOS Vision (accurate, zh-Hans): near character-exact on the same page (2-3 minor
    errors, e.g. one homophone swap) -- the clear winner, and it's local/free/fast
    (no network round-trip), which is what makes OCR-ing thousands of pages practical.
This ties this stage to running on macOS (PyObjC + Vision.framework). If this pipeline
ever needs to run on Linux CI, swap in PaddleOCR (best non-Apple option for Chinese) --
same ocr_pages.jsonl contract.

Output: data/pipeline/{dataset}/splits/{split}/ocr_pages.jsonl, one row per page:
  {page_index (0-based, into the source PDF), text}

Resumable: if ocr_pages.jsonl already has a row for a page_index, that page is skipped,
so re-running after a crash or to extend the page range only OCRs new pages.
"""
import argparse

import pdfplumber
import Quartz
import Vision
from Foundation import NSData
from tqdm import tqdm

from core.common import read_jsonl, work_dir, write_jsonl

RECOGNITION_LANGUAGES = ["zh-Hans", "en-US"]


def ocr_jpeg_bytes(jpeg_bytes: bytes) -> str:
    ns_data = NSData.dataWithBytes_length_(jpeg_bytes, len(jpeg_bytes))
    src = Quartz.CGImageSourceCreateWithData(ns_data, None)
    if src is None:
        return ""
    cg_image = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cg_image is None:
        return ""

    lines = []

    def handler(request, error):
        if error:
            return
        for obs in request.results():
            candidate = obs.topCandidates_(1)
            if candidate:
                lines.append(candidate[0].string())

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(handler)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    request.setRecognitionLanguages_(RECOGNITION_LANGUAGES)

    req_handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    ok, err = req_handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision OCR failed: {err}")
    return "\n".join(lines)


def extract_page_jpeg(page) -> bytes | None:
    """Each page in these source PDFs is exactly one full-page DCTDecode (JPEG) image."""
    if not page.images:
        return None
    return page.images[0]["stream"].get_data()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True, help="output subdir under data/pipeline/TCM/splits/")
    ap.add_argument("--pdf", required=True, help="path to the source PDF")
    ap.add_argument("--start-page", type=int, required=True, help="0-based, inclusive")
    ap.add_argument("--end-page", type=int, required=True, help="0-based, inclusive")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    out_path = wd / "ocr_pages.jsonl"
    rows = list(read_jsonl(out_path))
    done = {r["page_index"] for r in rows}

    with pdfplumber.open(args.pdf) as pdf:
        page_indices = [i for i in range(args.start_page, args.end_page + 1) if i not in done]
        for i in tqdm(page_indices, desc="OCR pages"):
            page = pdf.pages[i]
            jpeg_bytes = extract_page_jpeg(page)
            text = ocr_jpeg_bytes(jpeg_bytes).strip() if jpeg_bytes is not None else ""
            rows.append({"page_index": i, "text": text})
            rows.sort(key=lambda r: r["page_index"])
            write_jsonl(out_path, rows)  # rewritten each page so a crash loses at most 1 page

    n_empty = sum(1 for r in rows if not r["text"])
    n_chars = sum(len(r["text"]) for r in rows)
    print(f"OCR'd {len(rows)} pages total ({n_empty} empty), {n_chars} chars -> {out_path}")


if __name__ == "__main__":
    main()
