import json
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

from lumepdf import core
from lumepdf.core import PdfError
from lumepdf.server import make_server


def make_pdf(path, pages=5):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(200, 300)
    with open(path, "wb") as fh:
        w.write(fh)
    return Path(path)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pdf = make_pdf(self.tmp / "a.pdf")

    def n(self, p):
        return len(PdfReader(str(p)).pages)

    def test_ranges(self):
        self.assertEqual(core.parse_ranges("1-2,5", 5), [0, 1, 4])
        self.assertEqual(core.parse_ranges("4-", 5), [3, 4])
        self.assertEqual(core.parse_ranges("", 3), [0, 1, 2])
        with self.assertRaises(PdfError):
            core.parse_ranges("9", 5)
        with self.assertRaises(PdfError):
            core.parse_ranges("x", 5)

    def test_merge_extract_delete_reorder(self):
        b = make_pdf(self.tmp / "b.pdf", 2)
        self.assertEqual(self.n(core.merge([self.pdf, b], self.tmp / "m.pdf")), 7)
        self.assertEqual(self.n(core.extract_pages(self.pdf, "1-2", self.tmp / "e.pdf")), 2)
        self.assertEqual(self.n(core.delete_pages(self.pdf, "1", self.tmp / "d.pdf")), 4)
        self.assertEqual(self.n(core.reorder(self.pdf, "3,1", self.tmp / "r.pdf")), 2)
        with self.assertRaises(PdfError):
            core.delete_pages(self.pdf, "1-5", self.tmp / "x.pdf")

    def test_split_and_rotate(self):
        z = core.split(self.pdf, "", self.tmp / "s.zip")
        self.assertEqual(len(zipfile.ZipFile(z).namelist()), 5)
        z = core.split(self.pdf, "1-2,3-5", self.tmp / "s2.zip")
        self.assertEqual(len(zipfile.ZipFile(z).namelist()), 2)
        out = core.rotate(self.pdf, 90, "1", self.tmp / "rot.pdf")
        self.assertEqual(PdfReader(str(out)).pages[0].rotation, 90)
        self.assertEqual(PdfReader(str(out)).pages[1].rotation, 0)

    def test_compress_levels(self):
        for level in ("leve", "media", "forte"):
            self.assertEqual(self.n(core.compress(self.pdf, level, self.tmp / f"{level}.pdf")), 5)

    def test_images_and_back(self):
        img = self.tmp / "i.png"
        Image.new("RGBA", (50, 80), (255, 0, 0, 128)).save(img)
        pdf = core.images_to_pdf([img, img], self.tmp / "i.pdf")
        self.assertEqual(self.n(pdf), 2)
        z = core.pdf_to_images(pdf, "png", 72, "1", self.tmp / "i.zip")
        self.assertEqual(len(zipfile.ZipFile(z).namelist()), 1)

    def test_text_watermark_numbers(self):
        self.assertTrue(core.extract_text(self.pdf, self.tmp / "t.txt").read_text().startswith("--- Página 1"))
        self.assertEqual(self.n(core.watermark(self.pdf, "X", self.tmp / "w.pdf")), 5)
        self.assertEqual(self.n(core.page_numbers(self.pdf, self.tmp / "n.pdf")), 5)
        with self.assertRaises(PdfError):
            core.watermark(self.pdf, " ", self.tmp / "w2.pdf")

    def test_protect_unlock(self):
        prot = core.protect(self.pdf, "segredo", self.tmp / "p.pdf")
        with self.assertRaises(PdfError):
            core.extract_pages(prot, "1", self.tmp / "o.pdf")
        self.assertEqual(self.n(core.extract_pages(prot, "1", self.tmp / "o.pdf", "segredo")), 1)
        with self.assertRaises(PdfError):
            core.unlock(prot, "errada", self.tmp / "u.pdf")
        self.assertFalse(PdfReader(str(core.unlock(prot, "segredo", self.tmp / "u.pdf"))).is_encrypted)


class ServerTests(unittest.TestCase):
    def test_upload_tool_download(self):
        srv = make_server()
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            tmp = Path(tempfile.mkdtemp())
            pdf = make_pdf(tmp / "a.pdf", 3)
            ids = []
            for _ in range(2):
                req = urllib.request.Request(base + "/api/upload?name=a.pdf", pdf.read_bytes(), method="POST")
                meta = json.load(urllib.request.urlopen(req))
                self.assertEqual(meta["pages"], 3)
                ids.append(meta["id"])
            body = json.dumps({"files": ids, "params": {}}).encode()
            req = urllib.request.Request(base + "/api/tool/merge", body, method="POST")
            res = json.load(urllib.request.urlopen(req))
            data = urllib.request.urlopen(base + res["download"]).read()
            self.assertTrue(data.startswith(b"%PDF"))
            thumb = urllib.request.urlopen(f"{base}/api/thumb/{ids[0]}/0?w=60").read()
            self.assertTrue(thumb.startswith(b"\xff\xd8"))
            self.assertIn(b"LumePDF", urllib.request.urlopen(base + "/").read())
        finally:
            srv.shutdown()
            srv.workspace.cleanup()


if __name__ == "__main__":
    unittest.main()
