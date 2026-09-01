from runpod_worker import density_heading_correction as heading


def test_heading_candidates_are_list_items_only():
    assert heading._CANDIDATE_LABELS == {"list_item"}


def test_text_items_cannot_enter_promotion_candidates():
    items = [
        {
            "label": "text",
            "is_candidate": False,
            "heading_density_score": 100.0,
            "text_length": 1,
            "height": 100.0,
            "body_height": 1.0,
            "gap_above": None,
        },
        {
            "label": "list_item",
            "is_candidate": True,
            "heading_density_score": 100.0,
            "text_length": 1,
            "height": 100.0,
            "body_height": 1.0,
            "gap_above": None,
        },
    ]

    promoted = heading.promote_candidates(items)

    assert [item["label"] for item in promoted] == ["list_item"]
