"""On-device image redaction via Apple Vision — strict fill-all, fail-closed.

macOS + Apple Silicon only (Apple Vision has no portable equivalent). The text
engine can't see inside images, so by default every image fails closed (refused).
When enabled the strategy is deliberately STRICT and geometry-first:

- Cover EVERY detected text region and face with a SOLID OPAQUE box — never blur
  or pixelate (those are mathematically reversible).
- Never gate the fill on what OCR *read*: Apple Vision's transcription is
  unreliable (it garbles secrets — observed "AKIAIOSFODNN7EXAMPLE" → "…EXAMI"),
  so a detector-gated fill would leave the very keys we must hide on the wire.
- Use BOTH recognition (VNRecognizeText) and detection (VNDetectTextRectangles —
  detection recall > recognition recall) plus face rectangles, so detected-but-
  unreadable text is still covered.
- After filling, RE-SCAN the filled image with the SAME detectors (recognition
  + detection + faces) and REFUSE (raise) on ANY residual region — the
  fail-closed safety net, with no confidence tolerance (text re-reading even at
  low confidence is still readable, so it must not ship).

Recall ceiling (documented, not hidden): text Vision cannot detect AT ALL (very
low contrast, extreme rotation, tiny fonts) may be missed. Callers who cannot
tolerate that residual risk should keep images failing closed.
"""

from __future__ import annotations

import base64
import functools
import io
import re

# Inline image data URI: data:image/png;base64,<...>. Anything else (a remote
# http(s) URL, a non-image MIME) is not locally redactable → the caller fails closed.
_DATA_URI_RE = re.compile(r"^data:(?P<mime>image/[A-Za-z0-9.+-]+);base64,(?P<data>.+)$", re.DOTALL)
_PDF_DATA_URI_RE = re.compile(r"^data:application/pdf;base64,(?P<data>.+)$", re.DOTALL)

# Pad each fill box by this fraction of its size (OCR clips glyph edges + anti-alias).
_PAD = 0.10
# Provider media types we can decode + re-encode losslessly enough to redact.
_SUPPORTED: dict[str, str] = {"image/png": "PNG", "image/jpeg": "JPEG", "image/jpg": "JPEG"}
# PDF pages render at this multiple of their point size (72 DPI × 3 = 216 DPI) so
# small body text clears Vision's OCR floor (see _rasterize_pdf_page).
_PDF_RENDER_SCALE = 3


class ImageRedactionError(RuntimeError):
    """An image could not be SAFELY redacted → the caller must fail closed."""


@functools.lru_cache(maxsize=1)
def _stack():
    """Import the Vision + Quartz + Pillow stack once; return it or ``None``."""
    try:
        import Vision
        from Foundation import NSData
        from PIL import Image, ImageDraw

        return (Vision, NSData, Image, ImageDraw)
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def image_redaction_available() -> bool:
    """True only if Apple Vision OCR actually runs here (memoized self-test)."""
    stack = _stack()
    if stack is None:
        return False
    vision, nsdata_cls, image_cls, _ = stack
    try:
        buf = io.BytesIO()
        image_cls.new("RGB", (32, 32), "white").save(buf, "PNG")
        raw = buf.getvalue()
        nsdata = nsdata_cls.dataWithBytes_length_(raw, len(raw))
        handler = vision.VNImageRequestHandler.alloc().initWithData_options_(nsdata, {})
        req = vision.VNRecognizeTextRequest.alloc().init()
        handler.performRequests_error_([req], None)
        return True
    except Exception:
        return False


def _run(vision, nsdata_cls, raw: bytes, req) -> list:
    nsdata = nsdata_cls.dataWithBytes_length_(raw, len(raw))
    handler = vision.VNImageRequestHandler.alloc().initWithData_options_(nsdata, {})
    _ok, err = handler.performRequests_error_([req], None)
    if err is not None:
        raise ImageRedactionError(f"vision request failed: {err}")
    return list(req.results() or [])


def _detect_boxes(vision, nsdata_cls, raw: bytes) -> list[tuple[float, float, float, float]]:
    """All normalized (bottom-left) boxes to cover: recognized + detected text + faces."""
    boxes: list[tuple[float, float, float, float]] = []

    recognize = vision.VNRecognizeTextRequest.alloc().init()
    recognize.setRecognitionLevel_(vision.VNRequestTextRecognitionLevelAccurate)
    detect = vision.VNDetectTextRectanglesRequest.alloc().init()
    faces = vision.VNDetectFaceRectanglesRequest.alloc().init()

    for req in (recognize, detect, faces):
        for obs in _run(vision, nsdata_cls, raw, req):
            bb = obs.boundingBox()
            boxes.append((bb.origin.x, bb.origin.y, bb.size.width, bb.size.height))
    return boxes


def _to_pixel_rect(box, width: int, height: int) -> tuple[int, int, int, int]:
    """Normalized bottom-left box → padded integer top-left pixel rect."""
    x, y, w, h = box
    x -= w * _PAD
    y -= h * _PAD
    w *= 1 + 2 * _PAD
    h *= 1 + 2 * _PAD
    left = max(0, int(x * width))
    right = min(width, int((x + w) * width))
    # Flip Y: Vision's origin is bottom-left, Pillow's is top-left.
    top = max(0, int((1.0 - y - h) * height))
    bottom = min(height, int((1.0 - y) * height))
    return left, top, right, bottom


def redact_image_bytes(raw: bytes, media_type: str) -> bytes:
    """Return ``raw`` with every text region + face covered by an opaque box.

    Raises :class:`ImageRedactionError` on ANY doubt — Vision unavailable,
    unsupported/undecodable format, a Vision failure, or readable text surviving
    the re-verify pass — so the caller forwards NOTHING (fail-closed).
    """
    stack = _stack()
    if stack is None:
        raise ImageRedactionError("apple vision is unavailable on this machine")
    vision, nsdata_cls, image_cls, imagedraw_cls = stack

    fmt = _SUPPORTED.get((media_type or "").lower())
    if fmt is None:
        raise ImageRedactionError(f"unsupported image media type {media_type!r}")
    try:
        img = image_cls.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise ImageRedactionError(f"cannot decode image: {exc}") from exc

    width, height = img.size
    boxes = _detect_boxes(vision, nsdata_cls, raw)
    draw = imagedraw_cls.Draw(img)
    for box in boxes:
        left, top, right, bottom = _to_pixel_rect(box, width, height)
        if right > left and bottom > top:
            draw.rectangle([left, top, right, bottom], fill=(0, 0, 0))

    out = io.BytesIO()
    img.save(out, fmt)
    redacted = out.getvalue()

    # Fail-closed safety net: re-scan the FILLED image with the SAME detectors.
    # A clean fill leaves zero regions; ANY residual (recognized text, detected
    # text rectangle, or face) means the fill missed something → refuse. No
    # confidence tolerance — pass-1 fills unconditionally, so any survivor is real.
    if _detect_boxes(vision, nsdata_cls, redacted):
        raise ImageRedactionError(
            "text or a face survived redaction; refusing to forward (fail-closed)"
        )
    return redacted


def redact_data_uri(uri: str) -> str:
    """Redact an inline ``data:image/...;base64,...`` URI → a new data URI.

    Raises :class:`ImageRedactionError` when ``uri`` is not an inline base64
    image data URI (e.g. a remote URL) or when redaction fails — so the calling
    adapter fails closed.
    """
    match = _DATA_URI_RE.match(uri or "")
    if match is None:
        raise ImageRedactionError("not an inline base64 image data URI")
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except (ValueError, TypeError) as exc:
        raise ImageRedactionError(f"data URI base64 is invalid: {exc}") from exc
    redacted = redact_image_bytes(raw, match.group("mime"))
    return f"data:{match.group('mime')};base64,{base64.b64encode(redacted).decode('ascii')}"


def _rasterize_pdf_page(quartz, doc, page_number: int) -> bytes:
    """Render one PDF page (white-backed) to PNG bytes via Quartz, at 3× scale.

    The media box is in POINTS (72/inch), so rendering 1:1 is 72 DPI — at which
    9-12pt body text is ~9-12px, at/below Vision's OCR floor. Vision would then
    miss it AND the re-verify (run on the same raster) would miss it too, a
    silent leak. Rendering at 3× (216 DPI) lifts small text above the floor.
    """
    page = quartz.CGPDFDocumentGetPage(doc, page_number)
    rect = quartz.CGPDFPageGetBoxRect(page, quartz.kCGPDFMediaBox)
    scale = _PDF_RENDER_SCALE
    width = max(1, int(rect.size.width * scale))
    height = max(1, int(rect.size.height * scale))
    cs = quartz.CGColorSpaceCreateDeviceRGB()
    ctx = quartz.CGBitmapContextCreate(None, width, height, 8, 0, cs, quartz.kCGImageAlphaPremultipliedLast)
    if ctx is None:
        raise ImageRedactionError("could not create a bitmap context for a PDF page")
    quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    quartz.CGContextFillRect(ctx, quartz.CGRectMake(0, 0, width, height))
    quartz.CGContextScaleCTM(ctx, scale, scale)  # points → 3× pixels so small text is OCR-able
    quartz.CGContextDrawPDFPage(ctx, page)
    cgimage = quartz.CGBitmapContextCreateImage(ctx)
    out = quartz.CFDataCreateMutable(None, 0)
    dest = quartz.CGImageDestinationCreateWithData(out, "public.png", 1, None)
    quartz.CGImageDestinationAddImage(dest, cgimage, None)
    if not quartz.CGImageDestinationFinalize(dest):
        raise ImageRedactionError("could not rasterize a PDF page")
    return bytes(out)


def redact_pdf_bytes(raw: bytes) -> bytes:
    """Redact a PDF by rasterizing each page → opaque-fill → re-verify → reflatten.

    There is no sound text-layer redaction (a black box leaves selectable glyphs,
    and embedded raster images leak), so every page is rendered to a bitmap, run
    through the same strict image pipeline (which REFUSES if any readable text
    survives), and the redacted pages are reassembled into a new flattened PDF —
    the searchable text layer is intentionally dropped. Raises
    :class:`ImageRedactionError` on ANY doubt (Vision unavailable, undecodable
    PDF, or a page that fails re-verify), so the caller fails closed.
    """
    stack = _stack()
    if stack is None:
        raise ImageRedactionError("apple vision is unavailable on this machine")
    _vision, _nsdata_cls, image_cls, _draw = stack
    try:
        import Quartz
        from CoreFoundation import CFDataCreate
    except Exception as exc:  # pragma: no cover — gated by _stack() above
        raise ImageRedactionError(f"quartz unavailable: {exc}") from exc

    data = CFDataCreate(None, raw, len(raw))
    provider = Quartz.CGDataProviderCreateWithCFData(data)
    doc = Quartz.CGPDFDocumentCreateWithProvider(provider)
    if doc is None:
        raise ImageRedactionError("cannot open PDF")
    pages_total = Quartz.CGPDFDocumentGetNumberOfPages(doc)
    if pages_total < 1:
        raise ImageRedactionError("PDF has no pages")

    redacted_pages = []
    for page_number in range(1, pages_total + 1):
        page_png = _rasterize_pdf_page(Quartz, doc, page_number)
        clean_png = redact_image_bytes(page_png, "image/png")  # re-verifies per page
        redacted_pages.append(image_cls.open(io.BytesIO(clean_png)).convert("RGB"))

    out = io.BytesIO()
    redacted_pages[0].save(out, "PDF", save_all=True, append_images=redacted_pages[1:], resolution=72.0)
    return out.getvalue()


def redact_pdf_data_uri(uri: str) -> str:
    """Redact an inline ``data:application/pdf;base64,...`` URI → a new data URI.

    Raises :class:`ImageRedactionError` if ``uri`` is not an inline base64 PDF
    data URI or redaction fails — so the calling adapter fails closed.
    """
    match = _PDF_DATA_URI_RE.match(uri or "")
    if match is None:
        raise ImageRedactionError("not an inline base64 application/pdf data URI")
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except (ValueError, TypeError) as exc:
        raise ImageRedactionError(f"pdf data URI base64 is invalid: {exc}") from exc
    redacted = redact_pdf_bytes(raw)
    return f"data:application/pdf;base64,{base64.b64encode(redacted).decode('ascii')}"
