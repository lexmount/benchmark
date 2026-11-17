"""Auditable, opt-in repair of OSWorld's URL-to-reference-PDF getter.

This is not loaded by the frozen v3 run.  Install it before DesktopEnv.reset()
only in a separately identified technical re-evaluation.  Task JSON,
Page.printToPDF options and the original compare_pdfs metric are unchanged.

Sources actually inspected:
* OSWorld 5123bfdbbc34b947bcffcff564abc62d0ab7072d, chrome.py:get_pdf_from_url
  https://github.com/xlang-ai/OSWorld/blob/5123bfdbbc34b947bcffcff564abc62d0ab7072d/desktop_env/evaluators/getters/chrome.py#L1424
* Puppeteer 1424aab23f3c0a8948c4f95d9e673bcc9f707aad, createPDFStream:
  await document.fonts.ready before Page.printToPDF.
  https://github.com/puppeteer/puppeteer/blob/1424aab23f3c0a8948c4f95d9e673bcc9f707aad/packages/puppeteer-core/src/cdp/Page.ts#L1393
* https://playwright.dev/python/docs/api/class-page#page-goto
  networkidle is discouraged; document/resource readiness is checked instead.
* Playwright v1.64.1, Chromium._connectOverCDPImpl: CDP transport ownership.
  https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/src/server/chromium/chromium.ts#L103-L151
* https://docs.mathjax.org/en/v3.2/web/typeset.html#handling-asynchronous-typesetting
  startup.promise includes initial asynchronous typesetting.  The affected
  article actually loads an asynchronous MathJax 3 script; a configuration
  object alone is therefore not evidence of completed typesetting.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import logging
import os
from pathlib import Path
import tempfile
import time

logger = logging.getLogger(__name__)
REPAIR_VERSION = "reference-pdf-readiness-v1"
UPSTREAM_COMMIT = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
TIMEOUT_MS = 60000
MAX_RETRIES = 3


class ReferenceUnavailable(RuntimeError):
    """A valid reference was unavailable; this is not an Agent score of zero."""


def sync_playwright():
    """Load the pinned host dependency only when a browser is needed."""
    from playwright.sync_api import sync_playwright as start
    return start()


def source_provenance() -> dict:
    return {
        "repair_version": REPAIR_VERSION,
        "repair_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "upstream_commit": UPSTREAM_COMMIT,
        "changed_getter": "desktop_env.evaluators.getters.chrome.get_pdf_from_url",
        "metric_unchanged": "desktop_env.evaluators.metrics.chrome.compare_pdfs",
    }


def validate_pdf(path: str | Path) -> dict:
    """Parse every page and reject corrupt, zero-page or content-free PDFs.

    Text is not required: image/vector PDFs can be legitimate.  The unchanged
    text-comparison metric remains responsible for scoring their contents.
    """
    try:
        import fitz
        pdf_path = Path(path)
        data = pdf_path.read_bytes()
        with fitz.open(stream=data, filetype="pdf") as document:
            if not document.is_pdf or document.needs_pass or document.page_count < 1:
                raise ValueError("PDF must be readable, unencrypted and contain pages")
            text_chars = 0
            has_content = False
            for page in document:
                text = page.get_text().strip()
                text_chars += len(text)
                has_content = has_content or bool(text or page.get_images() or page.get_drawings())
            if not has_content:
                raise ValueError("PDF contains no text, image or drawing content")
            return {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "pages": document.page_count,
                "text_chars": text_chars,
            }
    except ReferenceUnavailable:
        raise
    except Exception as error:
        raise ReferenceUnavailable(f"Invalid reference PDF: {type(error).__name__}: {error}") from error


# The deadline is inside the evaluated promise, because Playwright evaluate()
# itself has no timeout parameter.  No global network-idle condition is used.
_RESOURCE_READINESS = r"""async ({timeoutMs}) => {
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('Printable resources not ready before deadline')), timeoutMs);
  });
  const prepare = async () => {
    const mathScript = [...document.scripts].some(s => /mathjax/i.test(s.src));
    let mathVersion = null;
    if (mathScript || window.MathJax) {
      // An inline MathJax configuration can exist before the async script loads.
      while (!(window.MathJax && ((MathJax.startup && MathJax.startup.promise) ||
                                  (MathJax.Hub && MathJax.Hub.Queue)))) {
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      mathVersion = MathJax.version || null;
      if (MathJax.startup && MathJax.startup.promise) await MathJax.startup.promise;
      else await new Promise(resolve => MathJax.Hub.Queue(resolve));
    }
    // Make deferred images eligible for the same full-document print.  This
    // changes loading priority, not source URLs or page content.
    const images = [...document.images].filter(img => {
      const style = getComputedStyle(img);
      return (img.currentSrc || img.src) && style.display !== 'none' && style.visibility !== 'hidden';
    });
    await Promise.all(images.map(async img => {
      img.loading = 'eager';
      await img.decode();
      if (!img.naturalWidth || !img.naturalHeight) throw new Error('Printable image has no decoded pixels');
    }));
    if (document.fonts) await document.fonts.ready;
    // Let layout observe the final image/font/math dimensions.
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const body = document.body;
    if (!body || !(body.innerText.trim() || body.querySelector('img,svg,canvas'))) {
      throw new Error('Document has no printable body content');
    }
    return {mathjax_version: mathVersion, image_count: images.length,
            graphic_count: body.querySelectorAll('svg,canvas').length,
            body_text_chars: body.innerText.trim().length,
            fonts_status: document.fonts ? document.fonts.status : null};
  };
  try { return await Promise.race([prepare(), deadline]); }
  finally { clearTimeout(timer); }
}"""


def get_pdf_from_url(env, config: dict) -> str:
    """Generate a validated reference through the VM's original Chrome CDP.

    A valid existing destination is reusable.  Invalid destinations are never
    treated as references.  On failure an exception is raised and no fallback
    or zero-score placeholder is written.  Use a new cache directory when
    repairing an archived run so that its original artifacts stay immutable.
    """
    destination = Path(env.cache_dir) / config["dest"]
    if destination.is_file():
        try:
            validate_pdf(destination)
            return str(destination)
        except ReferenceUnavailable:
            logger.warning("Ignoring invalid cached reference PDF: %s", destination)

    endpoint = f"http://{env.vm_ip}:{env.chromium_port}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(MAX_RETRIES):
        temporary_path = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(endpoint, timeout=TIMEOUT_MS)
                page = None
                session = None
                try:
                    # browser.new_page() also owns a temporary context.  Use the
                    # original VM context and close only this newly created page.
                    if not browser.contexts:
                        raise ReferenceUnavailable("Original Chrome has no existing browser context")
                    page = browser.contexts[0].new_page()
                    page.set_default_timeout(TIMEOUT_MS)
                    response = page.goto(config["path"], wait_until="domcontentloaded", timeout=TIMEOUT_MS)
                    if response is None or response.status >= 400:
                        status = None if response is None else response.status
                        raise ReferenceUnavailable(f"Reference navigation returned HTTP {status}")
                    if page.url.startswith(("chrome-error:", "about:blank")):
                        raise ReferenceUnavailable("Reference navigation did not reach a document")
                    page.wait_for_load_state("load", timeout=TIMEOUT_MS)
                    page.emulate_media(media="print")
                    readiness = page.evaluate(_RESOURCE_READINESS, {"timeoutMs": TIMEOUT_MS})
                    if not isinstance(readiness, dict) or not any(readiness.get(key, 0) for key in ("body_text_chars", "image_count", "graphic_count")):
                        raise ReferenceUnavailable("Reference document did not confirm printable readiness")
                    session = page.context.new_cdp_session(page)
                    # Preserve the exact official defaults and task overrides.
                    parameters = {"printBackground": True, **config.get("print_options", {})}
                    result = session.send("Page.printToPDF", parameters)
                    pdf_bytes = base64.b64decode(result["data"], validate=True)
                    descriptor, temporary_name = tempfile.mkstemp(prefix=".reference-", suffix=".pdf", dir=destination.parent)
                    temporary_path = Path(temporary_name)
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(pdf_bytes)
                    validation = validate_pdf(temporary_path)
                    os.replace(temporary_path, destination)
                    temporary_path = None
                    logger.info("Reference PDF validated: %s; readiness=%s; validation=%s", destination, readiness, validation)
                    return str(destination)
                finally:
                    if session is not None:
                        try:
                            session.detach()
                        except Exception:
                            logger.warning("Could not detach owned reference CDP session", exc_info=True)
                    if page is not None:
                        try:
                            page.close()
                        except Exception:
                            logger.warning("Could not close owned reference page", exc_info=True)
                    # Browser/context ownership stays with OSWorld.  Exiting
                    # sync_playwright releases only our Playwright connection.
        except Exception as error:
            last_error = error
            logger.warning("Reference generation attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, error)
            if attempt + 1 < MAX_RETRIES:
                time.sleep(1)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    raise ReferenceUnavailable(f"Reference PDF unavailable after {MAX_RETRIES} attempts: {last_error}") from last_error


def install_getter_patch() -> dict:
    """Patch only the getter, before reset binds DesktopEnv getter callables.

    This performs no browser operations and changes no task, metric, postconfig
    or files in the frozen upstream checkout.  Existing DesktopEnv instances
    that have already reset must not be reused for a repaired evaluation.
    """
    chrome = importlib.import_module("desktop_env.evaluators.getters.chrome")
    getters = importlib.import_module("desktop_env.evaluators.getters")
    chrome.get_pdf_from_url = get_pdf_from_url
    getters.get_pdf_from_url = get_pdf_from_url
    return {**source_provenance(), "patched_exports": [
        "desktop_env.evaluators.getters.chrome.get_pdf_from_url",
        "desktop_env.evaluators.getters.get_pdf_from_url",
    ], "install_before_reset": True}
