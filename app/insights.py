"""Learning insights derived from a learner's stored answers (pure functions, no I/O)."""
from __future__ import annotations


def learning_insights(records: list[dict]) -> dict:
    """First-attempt vs repeat accuracy, and accuracy when the learner said "sure" vs "guess"."""
    seen: set[str] = set()
    new_correct = new_total = repeat_correct = repeat_total = 0
    confidence = {"sure": {"correct": 0, "total": 0}, "guess": {"correct": 0, "total": 0}}
    for record in records:
        first_attempt = record["question_id"] not in seen
        seen.add(record["question_id"])
        correct = bool(record["correct"])
        if first_attempt:
            new_total += 1
            new_correct += int(correct)
        else:
            repeat_total += 1
            repeat_correct += int(correct)
        bucket = confidence[record["confidence"]]
        bucket["total"] += 1
        bucket["correct"] += int(correct)

    def accuracy(correct: int, total: int) -> float | None:
        return correct / total if total else None

    return {
        "new_questions": {"correct": new_correct, "total": new_total, "accuracy": accuracy(new_correct, new_total)},
        "repeat_questions": {
            "correct": repeat_correct, "total": repeat_total, "accuracy": accuracy(repeat_correct, repeat_total),
        },
        "confidence": {
            name: {**values, "accuracy": accuracy(values["correct"], values["total"])}
            for name, values in confidence.items()
        },
    }
