"""베이스 모델 vs QLoRA 튜닝 모델 비교. **RunPod GPU Pod 에서 돈다.**

산출물 보고서 4장(정량 성능 비교)의 숫자가 여기서 나온다. 손으로 채우지 않는다.

    python ml/sllm/evaluate.py --base Qwen/Qwen3-4B-Instruct \
                               --adapter ml/sllm/adapter

**무엇을 재는가.** 평가 문서는 학습에 한 번도 안 들어간 둘이다
(`build_dataset.py` 의 `EVAL_DOCS`).

| 지표 | 뜻 |
|---|---|
| schema_ok | 출력이 `ExtractionResult` 로 파싱되는 비율. **작은 모델이 튜닝 전에 가장 많이 틀리는 곳** |
| field_f1 | 교사가 뽑은 업무 제목 집합과의 F1 (정규화 후 부분일치) |
| evidence_ok | 근거 ref 를 제공된 범위(E1..En) 안에서만 인용한 비율 |
| latency_ms | 표본당 생성 시간 중앙값 |

**정확도라고 부르지 않는다.** 교사 출력이 정답이라는 전제 위의 일치도이므로
`field_f1` 로 적는다. 보고서에도 그 한계를 같이 쓴다.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def title_f1(pred_titles: list[str], gold_titles: list[str]) -> float:
    """제목 집합의 F1. 완전일치는 너무 빡빡해 정규화 후 포함관계도 인정한다."""

    if not pred_titles and not gold_titles:
        return 1.0
    if not pred_titles or not gold_titles:
        return 0.0
    p = [norm(t) for t in pred_titles]
    g = [norm(t) for t in gold_titles]
    matched = 0
    used: set[int] = set()
    for a in p:
        for j, b in enumerate(g):
            if j in used or not a or not b:
                continue
            if a == b or a in b or b in a:
                matched += 1
                used.add(j)
                break
    prec = matched / len(p)
    rec = matched / len(g)
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def evaluate(generate, rows: list[dict], label: str) -> dict:
    from services.task_extraction.service import ExtractionResult

    schema_ok = 0
    ev_ok = 0
    f1s: list[float] = []
    lat: list[float] = []

    for i, row in enumerate(rows, start=1):
        msgs = row["messages"]
        gold = json.loads(msgs[2]["content"])
        gold_titles = [t.get("title", "") for t in gold.get("tasks", [])]
        allowed = set(re.findall(r"'ref': '(E\d+)'", msgs[1]["content"]))

        t0 = time.perf_counter()
        text = generate(msgs[0]["content"], msgs[1]["content"])
        lat.append((time.perf_counter() - t0) * 1000)

        # 모델이 코드펜스를 두르는 경우가 흔하다 — 벗겨서 판정한다
        body = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        try:
            parsed = ExtractionResult.model_validate_json(body)
        except Exception:  # noqa: BLE001
            f1s.append(0.0)
            print(f"  [{label} {i}/{len(rows)}] 스키마 실패")
            continue

        schema_ok += 1
        pred_titles = [t.title for t in parsed.tasks]
        f1s.append(title_f1(pred_titles, gold_titles))
        refs = {r for t in parsed.tasks for r in t.evidence_refs}
        if refs and refs <= allowed:
            ev_ok += 1
        print(f"  [{label} {i}/{len(rows)}] tasks={len(parsed.tasks)} f1={f1s[-1]:.2f}")

    n = len(rows)
    return {
        "samples": n,
        "schema_ok": round(schema_ok / n, 4) if n else 0.0,
        "field_f1": round(sum(f1s) / n, 4) if n else 0.0,
        "evidence_ok": round(ev_ok / n, 4) if n else 0.0,
        "latency_ms_median": round(statistics.median(lat), 1) if lat else 0.0,
    }


def build_generator(base: str, adapter: str | None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    quant = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tok = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base, quantization_config=quant, dtype=torch.bfloat16,
        device_map="auto", trust_remote_code=True,
    )
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()

    def generate(system: str, user: str) -> str:
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True,
        )
        ids = tok(prompt, return_tensors="pt", truncation=True, max_length=4096).to(model.device)
        with torch.no_grad():
            out = model.generate(
                **ids, max_new_tokens=1024, do_sample=False,
                pad_token_id=tok.pad_token_id or tok.eos_token_id,
            )
        return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

    return generate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-4B-Instruct")
    ap.add_argument("--adapter", default=str(HERE / "adapter"))
    ap.add_argument("--out", default=str(HERE / "eval_result.json"))
    args = ap.parse_args()

    rows = load_jsonl(HERE / "data" / "eval.jsonl")
    print(f"평가 표본 {len(rows)}건 (학습에 안 들어간 문서)\n")

    print("=== 베이스 모델 ===")
    base_metrics = evaluate(build_generator(args.base, None), rows, "base")
    print("\n=== 튜닝 모델 ===")
    tuned_metrics = evaluate(build_generator(args.base, args.adapter), rows, "tuned")

    result = {"base_model": args.base, "adapter": args.adapter,
              "base": base_metrics, "tuned": tuned_metrics}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 56)
    print(f"{'지표':<20}{'베이스':>12}{'튜닝':>12}{'변화':>12}")
    print("-" * 56)
    for k in ("schema_ok", "field_f1", "evidence_ok", "latency_ms_median"):
        b, t = base_metrics[k], tuned_metrics[k]
        d = f"{t - b:+.4f}" if k != "latency_ms_median" else f"{t - b:+.1f}"
        print(f"{k:<20}{b:>12}{t:>12}{d:>12}")
    print("=" * 56)
    print(f"\n저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
