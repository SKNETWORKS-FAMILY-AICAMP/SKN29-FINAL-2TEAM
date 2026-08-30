"""검색 이미지의 서명 URL과 Docling provenance 계약."""

from django.core import signing
from django.test import SimpleTestCase, override_settings

from services.document_pipeline.crop_renderer import PictureCropError, _first_bbox
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
