"""검색 이미지의 서명 URL과 Docling provenance 계약."""

from unittest.mock import patch

from django.core import signing
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

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

    def test_crop_api_rejects_a_token_for_another_block(self):
        url = signed_picture_crop_url(block_id="BL001", doc_id="DC001", revision="REV1")
        token = url.split("token=", 1)[1]

        response = self.client.get(
            reverse("api_document_picture_crop", kwargs={"block_id": "BL002"}),
            {"token": token},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"], "이미지 crop 서명이 올바르지 않습니다."
        )

    @patch("apps.projects.api_views.render_picture_crop", return_value=b"\x89PNG\r\n")
    @patch("apps.projects.api_views.load_document", return_value=b"%PDF-1.7")
    @patch("apps.projects.api_views.document_exists", return_value=True)
    @patch("apps.projects.api_views.VectorSearchRepository.picture_crop_source")
    def test_crop_api_returns_the_current_pdf_picture_as_png(
        self,
        picture_crop_source,
        _document_exists,
        _load_document,
        _render_picture_crop,
    ):
        picture_crop_source.return_value = {
            "mime_type": "application/pdf",
            "storage_key": "documents/DC001/source.pdf",
            "src_locator": {
                "prov": [
                    {"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}
                ]
            },
        }
        url = signed_picture_crop_url(block_id="BL001", doc_id="DC001", revision="REV1")
        token = url.split("token=", 1)[1]

        response = self.client.get(
            reverse("api_document_picture_crop", kwargs={"block_id": "BL001"}),
            {"token": token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Content-Disposition"], 'inline; filename="BL001.png"')
        self.assertEqual(response.content, b"\x89PNG\r\n")
        picture_crop_source.assert_called_once_with(
            block_id="BL001", doc_id="DC001", revision="REV1"
        )

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
