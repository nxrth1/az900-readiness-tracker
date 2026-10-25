"""Content review workflow.

A question counts as reviewed only when a *person* has checked its wording, answer, rationale and topic
against the current Microsoft Learn skills outline and recorded the date. This tool makes that routine:

    python -m app.review status                 progress, by topic
    python -m app.review list --unreviewed      what is left (optionally --topic compute)
    python -m app.review show cc-01 cc-02       everything a reviewer needs, plus the Learn page to check against
    python -m app.review mark cc-01 cc-02       record today's date after you have checked them
    python -m app.review unmark cc-01           send a question back to "unchecked" (e.g. after editing it)

Who reviewed what is recorded in the commit or pull request that changes ``question_review.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date

from . import questions
from .learn import load_links
from .questions import TOPIC_NAMES, load_bank


def read_ledger() -> dict:
    return json.loads(questions.REVIEW_FILE.read_text(encoding="utf-8"))


def write_ledger(ledger: dict) -> None:
    """Atomic replace: a crash mid-write can never leave a half-written ledger."""
    path = questions.REVIEW_FILE
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".review-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_review(ids: list[str], reviewed_on: date | None) -> list[str]:
    """Set (or clear, with None) the review date for ``ids``. Returns the ids changed."""
    if reviewed_on is not None and reviewed_on > date.today():
        raise ValueError("a review date cannot be in the future")
    bank = load_bank()
    unknown = [i for i in ids if i not in bank]
    if unknown:
        raise ValueError(f"unknown question id(s): {', '.join(unknown)}")
    ledger = read_ledger()
    for question_id in ids:
        ledger["questions"][question_id] = reviewed_on.isoformat() if reviewed_on else None
    write_ledger(ledger)
    return ids


def status() -> dict:
    ledger = read_ledger()["questions"]
    bank = load_bank()
    by_topic: dict[str, list[int]] = {}
    for qid, q in bank.items():
        done, total = by_topic.setdefault(q.topic, [0, 0])
        by_topic[q.topic] = [done + (ledger.get(qid) is not None), total + 1]
    return {
        "reviewed": sum(done for done, _ in by_topic.values()),
        "total": len(bank),
        "by_topic": {t: {"reviewed": d, "total": n} for t, (d, n) in by_topic.items()},
        "skills_measured_as_of": read_ledger().get("skills_measured_as_of"),
    }


def _show(question_id: str) -> str:
    q = load_bank()[question_id]
    reviewed = read_ledger()["questions"].get(question_id)
    link = load_links()["topics"][q.topic]
    lines = [
        f"{q.id}  [{TOPIC_NAMES[q.topic]}]  difficulty {q.difficulty}  reviewed: {reviewed or 'NOT YET'}",
        f"Q: {q.q}",
    ]
    for i, option in enumerate(q.options):
        mark = "  <-- correct" if i == q.answer else ""
        lines.append(f"  {chr(65 + i)}. {option}{mark}")
        if i != q.answer:
            lines.append(f"       why wrong: {q.why_not[i]}")
    lines += [f"Why: {q.why}", f"Check against: {link['title']}", f"               {link['url']}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.review", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    ls = sub.add_parser("list")
    ls.add_argument("--unreviewed", action="store_true")
    ls.add_argument("--reviewed", action="store_true")
    ls.add_argument("--topic")
    for name in ("show", "mark", "unmark"):
        cmd = sub.add_parser(name)
        cmd.add_argument("ids", nargs="+")
        if name == "mark":
            cmd.add_argument("--date", type=date.fromisoformat, default=None, help="default: today")
            cmd.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            info = status()
            print(f"Reviewed {info['reviewed']}/{info['total']} against the skills outline of {info['skills_measured_as_of']}")
            for topic, v in info["by_topic"].items():
                print(f"  {TOPIC_NAMES[topic]:<28} {v['reviewed']}/{v['total']}")
        elif args.command == "list":
            ledger = read_ledger()["questions"]
            for qid, q in load_bank().items():
                done = ledger.get(qid) is not None
                if (args.unreviewed and done) or (args.reviewed and not done) or (args.topic and q.topic != args.topic):
                    continue
                print(f"{qid:<8} {q.topic:<22} {ledger.get(qid) or '-'}")
        elif args.command == "show":
            bank = load_bank()
            for qid in args.ids:
                if qid not in bank:
                    raise ValueError(f"unknown question id(s): {qid}")
                print(_show(qid))
        elif args.command == "mark":
            if not args.yes:
                answer = input(f"Mark {len(args.ids)} question(s) as checked by a person against the current guide? [y/N] ")
                if answer.strip().lower() != "y":
                    print("Nothing changed.")
                    return 1
            done = set_review(args.ids, args.date or date.today())
            print(f"Marked {len(done)} question(s) reviewed. Commit question_review.json and name the reviewer in the message.")
        elif args.command == "unmark":
            print(f"Cleared {len(set_review(args.ids, None))} question(s).")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
