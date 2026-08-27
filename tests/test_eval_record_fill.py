from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.eval_record import _fill_case_from_db


class FillCaseFromDbTests(unittest.TestCase):
    def test_fills_missing_final_answer_and_tool_calls_from_db(self):
        case = {
            "case_id": "WF-001",
            "agent_run_id": "run-1",
            "human_rubric": {"total": 90},
        }
        with patch(
            "backend.db.evaluation.EvaluationResultRepository.fetch_agent_execution_summary",
            return_value={"final_answer": "복구된 답변", "tool_call_ids": ["tc-1"]},
        ):
            filled = _fill_case_from_db(case)

        self.assertEqual(filled["final_answer"], "복구된 답변")
        self.assertEqual(filled["tool_call_ids"], ["tc-1"])
        self.assertEqual(filled["human_rubric"], {"total": 90})

    def test_does_not_overwrite_existing_final_answer(self):
        # tool_call_ids도 이미 채워져 있어야 DB를 아예 안 부른다 — final_answer
        # 하나만 있고 tool_call_ids가 없으면, 그걸 채우려고 DB는 부르되
        # final_answer는 그대로 보존해야 한다(다음 테스트에서 별도 확인).
        case = {
            "case_id": "WF-001",
            "agent_run_id": "run-1",
            "final_answer": "사람이 이미 적어둔 답변",
            "tool_call_ids": ["existing-tc"],
        }
        with patch(
            "backend.db.evaluation.EvaluationResultRepository.fetch_agent_execution_summary",
            return_value={"final_answer": "DB 답변", "tool_call_ids": ["db-tc"]},
        ) as mock_fetch:
            filled = _fill_case_from_db(case)

        mock_fetch.assert_not_called()
        self.assertEqual(filled["final_answer"], "사람이 이미 적어둔 답변")
        self.assertEqual(filled["tool_call_ids"], ["existing-tc"])

    def test_fills_only_missing_field_and_preserves_the_other(self):
        case = {
            "case_id": "WF-001",
            "agent_run_id": "run-1",
            "final_answer": "사람이 이미 적어둔 답변",
        }
        with patch(
            "backend.db.evaluation.EvaluationResultRepository.fetch_agent_execution_summary",
            return_value={"final_answer": "DB 답변", "tool_call_ids": ["db-tc"]},
        ) as mock_fetch:
            filled = _fill_case_from_db(case)

        mock_fetch.assert_called_once_with("run-1")
        self.assertEqual(filled["final_answer"], "사람이 이미 적어둔 답변")
        self.assertEqual(filled["tool_call_ids"], ["db-tc"])

    def test_no_agent_run_id_skips_db_lookup(self):
        case = {"case_id": "WF-001"}
        with patch(
            "backend.db.evaluation.EvaluationResultRepository.fetch_agent_execution_summary",
        ) as mock_fetch:
            filled = _fill_case_from_db(case)

        mock_fetch.assert_not_called()
        self.assertEqual(filled, case)

    def test_db_returning_nothing_leaves_case_unfilled(self):
        case = {"case_id": "WF-001", "agent_run_id": "run-1"}
        with patch(
            "backend.db.evaluation.EvaluationResultRepository.fetch_agent_execution_summary",
            return_value={"final_answer": None, "tool_call_ids": []},
        ):
            filled = _fill_case_from_db(case)

        self.assertNotIn("final_answer", filled)
        self.assertNotIn("tool_call_ids", filled)


if __name__ == "__main__":
    unittest.main()
