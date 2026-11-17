"""Contract checks for the separate, opt-in reference getter repair.

No Chrome, VM or model is started.  Playwright boundaries are mocked; Node,
when installed, executes the actual readiness JavaScript against a tiny DOM.
The host's existing PyMuPDF, when installed, validates the real PDF fixture.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("osworld_reference_repair_contract", ROOT / "reference_repair.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def readable_pdf() -> bytes:
    """A self-contained one-page PDF with a standard font and real text content."""
    text = b"BT /F1 12 Tf 20 100 Td (Reference body ready.) Tj ET\n"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"endstream"]
    data, offsets = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    data += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return data


GOOD_PDF = readable_pdf()
ORIGINAL_PLACEHOLDER = b"%PDF-1.4\n%EOF\n"


class BrowserBoundary:
    def __init__(self, *, pdf=GOOD_PDF, readiness_error=None, status=200):
        self.pdf, self.readiness_error, self.status = pdf, readiness_error, status
        self.pages, self.print_calls, self.events = [], [], []
        self.browser = types.SimpleNamespace(contexts=[types.SimpleNamespace(new_page=self.new_page)],
                                            close=mock.Mock(side_effect=AssertionError("Original Chrome must stay open")))
        self.connect = mock.Mock(return_value=self.browser)
        self.playwright = types.SimpleNamespace(chromium=types.SimpleNamespace(connect_over_cdp=self.connect))

    def new_page(self):
        boundary = self
        class Page:
            url = "https://example.invalid/article"
            def __init__(self):
                self.context = types.SimpleNamespace(new_cdp_session=lambda page: self.session)
                self.session = types.SimpleNamespace(send=self.send, detach=mock.Mock())
                self.close = mock.Mock()
            def set_default_timeout(self, timeout):
                pass
            def goto(self, url, **kwargs):
                boundary.events.append(("goto", kwargs.get("wait_until")))
                if kwargs.get("wait_until") == "networkidle":
                    raise TimeoutError("Network never becomes idle")
                return None if boundary.status is None else types.SimpleNamespace(status=boundary.status)
            def wait_for_load_state(self, state, **kwargs):
                boundary.events.append(("load_state", state))
                if state == "networkidle":
                    raise TimeoutError("Network never becomes idle")
            def emulate_media(self, **kwargs):
                boundary.events.append(("media", kwargs["media"]))
            def evaluate(self, script, argument):
                boundary.events.append(("readiness", argument))
                if boundary.readiness_error:
                    raise boundary.readiness_error
                return {"body_text_chars": 21, "image_count": 0, "graphic_count": 0,
                        "fonts_status": "loaded", "mathjax_version": "3.2"}
            def send(self, method, parameters):
                boundary.print_calls.append((method, deepcopy(parameters)))
                boundary.events.append(("print", method))
                return {"data": base64.b64encode(boundary.pdf).decode()}
        page = Page()
        self.pages.append(page)
        return page

    def manager(self):
        playwright = self.playwright
        class Manager:
            def __enter__(self):
                return playwright
            def __exit__(self, *args):
                return False
        return Manager()


class ReferenceGetterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.env = types.SimpleNamespace(cache_dir=str(self.cache), vm_ip="127.0.0.1", chromium_port=19222)
        self.config = {"path": "https://example.invalid/article", "dest": "reference.pdf"}
        self.destination = self.cache / self.config["dest"]

    @staticmethod
    def validate_fixture(path):
        # The getter's validation boundary is mocked independently from its bytes
        # generation; real-fitZ checks below exercise the actual parser on 5090.
        data = Path(path).read_bytes()
        if data != GOOD_PDF:
            raise repair.ReferenceUnavailable("Reference fixture is unreadable or content-free")
        return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
                "pages": 1, "text_chars": 21}

    def invoke(self, browser, config=None):
        with mock.patch.object(repair, "sync_playwright", side_effect=browser.manager), \
                mock.patch.object(repair, "validate_pdf", side_effect=self.validate_fixture) as validate, \
                mock.patch.object(repair.time, "sleep"):
            result = repair.get_pdf_from_url(self.env, config or self.config)
        return result, validate

    def assert_only_owned_pages_closed(self, browser):
        browser.browser.close.assert_not_called()
        for page in browser.pages:
            page.close.assert_called_once()

    def test_network_never_idle_but_dom_fonts_ready_produces_valid_nonempty_pdf(self):
        browser = BrowserBoundary()
        path, validate = self.invoke(browser)
        self.assertEqual(Path(path).read_bytes(), GOOD_PDF)
        validate.assert_called_once()
        self.assertGreater(len(GOOD_PDF), len(ORIGINAL_PLACEHOLDER))
        self.assertIn(("goto", "domcontentloaded"), browser.events)
        self.assertIn(("load_state", "load"), browser.events)
        self.assertFalse(any(event[1] == "networkidle" for event in browser.events))
        self.assertLess(browser.events.index(("media", "print")),
                        browser.events.index(("print", "Page.printToPDF")))
        browser.connect.assert_called_once_with("http://127.0.0.1:19222", timeout=repair.TIMEOUT_MS)
        browser.pages[0].session.detach.assert_called_once()
        self.assert_only_owned_pages_closed(browser)
        self.assertEqual(list(self.cache.glob(".reference-*")), [])

    def test_original_task_print_options_are_forwarded_without_mutating_them(self):
        task = ROOT / "data/tasks/chrome/e1e75309-3ddb-4d09-92ec-de869c928143.json"
        original_bytes = task.read_bytes()
        config = json.loads(original_bytes)["evaluator"]["expected"]
        before = deepcopy(config)
        browser = BrowserBoundary()
        self.invoke(browser, config)
        self.assertEqual(browser.print_calls, [("Page.printToPDF", {"printBackground": True, **before["print_options"]})])
        self.assertEqual(config, before)
        self.assertEqual(task.read_bytes(), original_bytes)
        for side in ("marginTop", "marginBottom", "marginLeft", "marginRight"):
            self.assertEqual(browser.print_calls[0][1][side], 0)

    def test_default_print_parameters_are_the_original_defaults(self):
        browser = BrowserBoundary()
        self.invoke(browser)
        self.assertEqual(browser.print_calls, [("Page.printToPDF", {"printBackground": True})])

    def test_fonts_or_image_resource_failure_is_unavailable_not_a_placeholder_or_zero(self):
        browser = BrowserBoundary(readiness_error=TimeoutError("Printable font/image not ready"))
        with self.assertRaises(repair.ReferenceUnavailable):
            self.invoke(browser)
        self.assertFalse(self.destination.exists())
        self.assertFalse(browser.print_calls)
        self.assert_only_owned_pages_closed(browser)
        self.assertEqual(list(self.cache.glob(".reference-*")), [])

    def test_http_resource_failure_does_not_print_an_error_page(self):
        for status in (404, 503, None):
            with self.subTest(status=status):
                browser = BrowserBoundary(status=status)
                with self.assertRaises(repair.ReferenceUnavailable):
                    self.invoke(browser)
                self.assertFalse(browser.print_calls)
                self.assertFalse(self.destination.exists())
                self.assert_only_owned_pages_closed(browser)

    def test_corrupt_pdf_bytes_are_never_committed_to_reference_destination(self):
        browser = BrowserBoundary(pdf=ORIGINAL_PLACEHOLDER)
        with self.assertRaises(repair.ReferenceUnavailable):
            self.invoke(browser)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.cache.glob(".reference-*")), [])
        self.assert_only_owned_pages_closed(browser)

    def test_valid_cache_is_parsed_then_reused_without_browser_navigation(self):
        self.destination.write_bytes(GOOD_PDF)
        browser = BrowserBoundary()
        path, validate = self.invoke(browser)
        self.assertEqual(Path(path).read_bytes(), GOOD_PDF)
        validate.assert_called_once_with(self.destination)
        browser.connect.assert_not_called()
        self.assertEqual(browser.pages, [])

    def test_invalid_cache_is_not_reused_and_only_valid_replacement_is_committed(self):
        self.destination.write_bytes(ORIGINAL_PLACEHOLDER)
        browser = BrowserBoundary()
        path, validate = self.invoke(browser)
        self.assertEqual(Path(path).read_bytes(), GOOD_PDF)
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(len(browser.print_calls), 1)

    def test_invalid_cache_and_resource_failure_preserve_original_without_a_fake_reference(self):
        self.destination.write_bytes(ORIGINAL_PLACEHOLDER)
        browser = BrowserBoundary(readiness_error=RuntimeError("image failed"))
        with self.assertRaises(repair.ReferenceUnavailable):
            self.invoke(browser)
        self.assertEqual(self.destination.read_bytes(), ORIGINAL_PLACEHOLDER)
        self.assertEqual(list(self.cache.glob(".reference-*")), [])

    def test_install_changes_only_getter_exports_not_metric_or_task_bytes(self):
        original_metric = lambda *a: 0.731
        chrome = types.SimpleNamespace(get_pdf_from_url=lambda *a: "old", compare_pdfs=original_metric)
        getters = types.SimpleNamespace(get_pdf_from_url=chrome.get_pdf_from_url)
        modules = {"desktop_env.evaluators.getters.chrome": chrome, "desktop_env.evaluators.getters": getters}
        task = ROOT / "data/tasks/chrome/e1e75309-3ddb-4d09-92ec-de869c928143.json"
        before = task.read_bytes()
        with mock.patch.object(repair.importlib, "import_module", side_effect=modules.__getitem__) as imports:
            metadata = repair.install_getter_patch()
        self.assertIs(chrome.get_pdf_from_url, repair.get_pdf_from_url)
        self.assertIs(getters.get_pdf_from_url, repair.get_pdf_from_url)
        self.assertIs(chrome.compare_pdfs, original_metric)
        self.assertEqual(imports.call_count, 2)
        self.assertTrue(metadata["install_before_reset"])
        self.assertEqual(metadata["metric_unchanged"], "desktop_env.evaluators.metrics.chrome.compare_pdfs")
        self.assertEqual(task.read_bytes(), before)


@unittest.skipUnless(importlib.util.find_spec("fitz"), "Real PDF parser is provided by the 5090 OSWorld host environment")
class ActualPdfValidationTests(unittest.TestCase):
    def test_actual_parser_accepts_one_page_text_and_rejects_original_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reference.pdf"
            path.write_bytes(GOOD_PDF)
            validated = repair.validate_pdf(path)
            self.assertEqual(validated["pages"], 1)
            self.assertGreater(validated["text_chars"], 0)
            self.assertEqual(validated["sha256"], hashlib.sha256(GOOD_PDF).hexdigest())
            path.write_bytes(ORIGINAL_PLACEHOLDER)
            with self.assertRaises(repair.ReferenceUnavailable):
                repair.validate_pdf(path)


@unittest.skipUnless(shutil.which("node"), "Node is optional for actual resource-readiness JavaScript checks")
class ActualReadinessJavascriptTests(unittest.TestCase):
    def execute(self, setup):
        common = """
globalThis.window=globalThis;
globalThis.requestAnimationFrame=callback=>setImmediate(callback);
globalThis.getComputedStyle=()=>({display:'block',visibility:'visible'});
const events=[];
const body={innerText:'Reference body ready.',querySelector:()=>null,querySelectorAll:()=>[]};
const fonts={status:'loaded'};
Object.defineProperty(fonts,'ready',{get(){events.push('fonts-awaited');return Promise.resolve();}});
"""
        command = common + setup + "\nconst readiness=(" + repair._RESOURCE_READINESS + ");\n" + """
readiness({timeoutMs:500}).then(value=>{
 console.log(JSON.stringify({ok:true,value,events,settledBeforeRuntime:globalThis.settledBeforeRuntime}));
},error=>{console.log(JSON.stringify({ok:false,error:error.message,events}));});
"""
        result = subprocess.run([shutil.which("node"), "-e", command], capture_output=True, text=True, timeout=3, check=True)
        return json.loads(result.stdout)

    def test_inline_mathjax_config_waits_for_runtime_promise_before_images_and_fonts(self):
        result = self.execute("""
globalThis.MathJax={tex:{inlineMath:[['$','$']]}};
const image={src:'figure.png',currentSrc:'figure.png',naturalWidth:10,naturalHeight:10,
 decode:async()=>{events.push('image-decoded');}};
globalThis.document={scripts:[{src:'https://cdn.invalid/mathjax.js'}],images:[image],fonts,body};
globalThis.settledBeforeRuntime=true;
setTimeout(()=>{
 globalThis.settledBeforeRuntime=events.includes('fonts-awaited');
 globalThis.MathJax={version:'3.2.0',startup:{promise:new Promise(resolve=>setTimeout(()=>{
   events.push('math-resolved');resolve();
 },30))}};
},20);
""")
        self.assertTrue(result["ok"])
        self.assertFalse(result["settledBeforeRuntime"])
        self.assertEqual(result["value"]["mathjax_version"], "3.2.0")
        self.assertLess(result["events"].index("math-resolved"), result["events"].index("image-decoded"))
        self.assertLess(result["events"].index("image-decoded"), result["events"].index("fonts-awaited"))

    def test_failed_image_decode_rejects_instead_of_printing_incomplete_reference(self):
        result = self.execute("""
globalThis.document={scripts:[],fonts,body,images:[{
 src:'broken.png',currentSrc:'broken.png',naturalWidth:0,naturalHeight:0,
 decode:()=>Promise.reject(new Error('printable image unavailable'))
}]};
""")
        self.assertFalse(result["ok"])
        self.assertIn("image unavailable", result["error"])
        self.assertNotIn("fonts-awaited", result["events"])


if __name__ == "__main__":
    unittest.main()
