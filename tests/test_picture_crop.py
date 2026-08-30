"""검색 이미지의 서명 URL과 Docling provenance 계약."""

from django.core import signing
from django.test import SimpleTestCase, override_settings

from services.document_pipeline.crop_renderer import (
    PictureCropError,
    _first_bbox,
    render_picture_crop,
)
from services.document_pipeline.picture_crop import (
    read_picture_crop_token,
    signed_picture_crop_url,
)


@override_settings(
    PUBLIC_BACKEND_BASE_URL="https://api.example.com",
    DOCUMENT_PICTURE_CROP_TOKEN_MAX_AGE_SECONDS=900,
)
class PictureCropContractTests(SimpleTestCase):
    def test_signed_url_round_trips_exact_source_identity(self):
        url = signed_picture_crop_url(block_id="BL001", doc_id="DC001", revision="REV1")
        token = url.split("token=", 1)[1]

        self.assertEqual(
            read_picture_crop_token(token),
            {"block_id": "BL001", "doc_id": "DC001", "revision": "REV1"},
        )

    def test_tampered_token_is_rejected(self):
        url = signed_picture_crop_url(block_id="BL001", doc_id="DC001", revision="REV1")
        token = url.split("token=", 1)[1]

        with self.assertRaises(signing.BadSignature):
            read_picture_crop_token(token + "x")

    def test_first_valid_provenance_is_used(self):
        locator = {
            "prov": [
                {"page_no": None, "bbox": None},
                {"page_no": 2, "bbox": {"l": 1, "t": 9, "r": 8, "b": 2}},
            ]
        }

        self.assertEqual(_first_bbox(locator), (2, locator["prov"][1]["bbox"]))

    def test_missing_bbox_is_rejected(self):
        with self.assertRaises(PictureCropError):
            _first_bbox({"prov": [{"page_no": 1}]})

    def test_topleft와_bottomleft가_같은_pdf_영역을_crop한다(self):
        import pymupdf

        document = pymupdf.open()
        page = document.new_page(width=200, height=200)
        page.draw_rect(
            pymupdf.Rect(40, 50, 120, 130),
            color=(1, 0, 0),
            fill=(1, 0, 0),
        )
        pdf = document.tobytes()

        top_left = render_picture_crop(
            pdf,
            {
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 40,
                            "t": 50,
                            "r": 120,
                            "b": 130,
                            "coord_origin": "TOPLEFT",
                        },
                    }
                ]
            },
        )
        bottom_left = render_picture_crop(
            pdf,
            {
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 40,
                            "t": 150,
                            "r": 120,
                            "b": 70,
                            "coord_origin": "BOTTOMLEFT",
                        },
                    }
                ]
            },
        )

        self.assertEqual(top_left, bottom_left)
