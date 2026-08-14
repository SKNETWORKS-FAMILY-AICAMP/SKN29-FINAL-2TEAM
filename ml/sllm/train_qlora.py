"""업무 추출 sLLM QLoRA 학습. **RunPod GPU Pod 에서 돈다.**

로컬에서 돌리지 않는다 — 4bit 양자화와 bf16 학습에 CUDA 가 필요하다.

Pod 준비(RunPod 콘솔에서 Pod 생성 후 웹 터미널):

    pip install -U "transformers>=4.44" "peft>=0.12" "trl>=0.9" \
                   "bitsandbytes>=0.43" "accelerate>=0.33" datasets
    python ml/sllm/train_qlora.py --base Qwen/Qwen3-4B-Instruct

⚠ **컨테이너 디스크가 30GB 다.** 베이스 가중치(4B fp16 ≈ 8GB)와 어댑터,
캐시가 모두 여기 들어간다. 8B 를 쓰려면 디스크를 늘려서 Pod 을 만들 것.

QLoRA 를 고른 이유: RTX 5090 은 VRAM 32GB 다. 4B 를 4bit 로 올리면 학습 중
여유가 넉넉해 배치를 키울 수 있고, 어댑터만 저장하므로 결과물이 수십 MB 다
(가중치 파일을 산출물로 제출해야 하는데 8GB 를 낼 수는 없다).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-4B-Instruct", help="베이스 모델")
    ap.add_argument("--out", default=str(HERE / "adapter"), help="어댑터 저장 경로")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--maxlen", type=int, default=4096)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    rows = load_jsonl(DATA / "train.jsonl")
    print(f"학습 표본 {len(rows)}건")
    ds = Dataset.from_list([{"messages": r["messages"]} for r in rows])

    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # 4bit NF4 + 이중 양자화. bf16 연산으로 되돌려 계산한다.
    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        quantization_config=quant,
        dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    peft_cfg = LoraConfig(
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        # attention 과 MLP 를 모두 건다. attention 만 걸면 형식은 배워도
        # 필드 내용이 잘 안 붙는다.
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )

    cfg = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.accum,
        max_length=args.maxlen,
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=5,
        save_strategy="epoch",
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        report_to=[],
        # **정답(assistant 턴)에만 손실을 건다.** 근거 청크까지 외우게 하면
        # 프롬프트를 따라 쓰는 쪽으로 수렴한다.
        assistant_only_loss=True,
    )

    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds,
                         peft_config=peft_cfg, processing_class=tok)
    trainer.train()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)

    meta = {
        "base": args.base,
        "epochs": args.epochs, "lr": args.lr,
        "batch": args.batch, "accum": args.accum,
        "max_length": args.maxlen, "rank": args.rank, "alpha": args.alpha,
        "train_samples": len(rows),
    }
    (Path(args.out) / "train_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {args.out}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
