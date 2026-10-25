"""Exam-date study planner.

Turns the readiness report into a day-by-day schedule. The idea is the same as "biggest wins":
time goes where it raises the estimated exam score most.

* Need per topic = exam weight x (gap to the target score + a small bonus for topics we know little about).
* Total study minutes come from the learner's hours per week and chosen study days.
* A mock exam is scheduled about a week out (and again if the runway is long), and the last study day
  before the exam is a light review of weak topics and confident mistakes, never new material.
* Topic minutes are cut into short blocks and interleaved so the same topic is not crammed into one day.

Everything is deterministic, so it is easy to test.
"""
from __future__ import annotations

from datetime import date, timedelta

from .questions import TOPIC_WEIGHTS
from .scoring import GOAL_SCORE

BLOCK = 25          # minutes per study block
MIN_BLOCK = 10      # smallest leftover block worth scheduling
MOCK_MINUTES = 45   # a 40-question mock exam
MAX_DAYS = 120


class PlanError(ValueError):
    pass


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _needs(report: dict) -> dict[str, float]:
    needs = {}
    for t in report["topics"]:
        gap = max(0.0, GOAL_SCORE + 0.05 - t["score"])  # aim a little above the goal
        needs[t["id"]] = TOPIC_WEIGHTS[t["id"]] * (gap + 0.15 * (1 - t["coverage"]))
    if sum(needs.values()) <= 0:
        needs = dict(TOPIC_WEIGHTS)  # already strong everywhere: maintain evenly
    return needs


def build_plan(report: dict, today: date, exam: date, hours_per_week: float, study_days: list[int]) -> dict:
    if exam <= today:
        raise PlanError("The exam date must be after today.")
    if (exam - today).days > MAX_DAYS:
        raise PlanError(f"Pick an exam date within {MAX_DAYS} days so the plan stays realistic.")
    if not (0.5 <= hours_per_week <= 40):
        raise PlanError("Hours per week must be between 0.5 and 40.")
    days_set = sorted({d for d in study_days if 0 <= d <= 6})
    if not days_set:
        raise PlanError("Choose at least one study day.")

    runway = [today + timedelta(days=i) for i in range((exam - today).days)]  # today .. day before exam
    slots = [d for d in runway if d.weekday() in days_set]
    if not slots:
        raise PlanError("None of your study days fall before the exam date.")

    per_day = max(MIN_BLOCK, _round5(hours_per_week * 60 / len(days_set)))
    names = {t["id"]: t["name"] for t in report["topics"]}
    scores = {t["id"]: t["score"] for t in report["topics"]}
    needs = _needs(report)
    mis = [m["topic"] for m in report.get("misconceptions", [])]

    # --- reserve special days -------------------------------------------------------------
    last = slots[-1]
    light_day = last if (exam - last).days <= 2 else None  # final review day, only if it is right before the exam
    mock_days: list[date] = []
    if len(slots) >= 3:
        candidates = [d for d in slots if (exam - d).days >= 3 and d != light_day]
        if candidates:
            target = exam - timedelta(days=7)
            # closest study day to one week out (never later than 3 days before)
            mock_days.append(min(candidates, key=lambda d: abs((d - target).days)))
            if len(candidates) > 14:  # long runway: add a mid-point checkpoint
                mid = today + (exam - today) / 2
                extra = min((d for d in candidates if d not in mock_days), key=lambda d: abs((d - mid).days))
                mock_days.append(extra)
    mock_days.sort()

    cap: dict[date, int] = {}
    for d in slots:
        c = per_day
        if d in mock_days:
            c = max(per_day, MOCK_MINUTES + MIN_BLOCK)  # mock exam needs real time even on short days
        if d == light_day:
            c = max(MIN_BLOCK, _round5(per_day * 0.6))
        cap[d] = c

    # --- topic minutes budget -------------------------------------------------------------
    learn_cap = {d: cap[d] - (MOCK_MINUTES if d in mock_days else 0) for d in slots if d != light_day}
    total_learn = max(0, sum(learn_cap.values()))
    need_sum = sum(needs.values())
    remaining = {t: _round5(total_learn * needs[t] / need_sum) for t in needs}
    # topics that would get almost nothing are dropped so blocks stay meaningful
    remaining = {t: m for t, m in remaining.items() if m >= MIN_BLOCK}

    schedule: dict[date, list[dict]] = {d: [] for d in slots}
    seen: set[str] = set()

    for d in slots:
        blocks = schedule[d]
        if d in mock_days:
            blocks.append({"type": "mock", "topic": None, "name": "Mock exam", "minutes": MOCK_MINUTES,
                           "note": "40 questions, no feedback until the end. Then review every miss."})
        if d == light_day:
            focus = list(dict.fromkeys(mis + sorted(scores, key=lambda t: scores[t])))[:3]
            share = max(MIN_BLOCK, (cap[d] // max(1, len(focus)) // 5) * 5)
            for t in focus:
                blocks.append({"type": "review", "topic": t, "name": names[t], "minutes": share,
                               "note": "Light review only. Re-read your misses; no new material today."})
            continue
        room = learn_cap[d]
        used_today: set[str] = set()
        while room >= MIN_BLOCK and any(m >= MIN_BLOCK for m in remaining.values()):
            avail = [t for t, m in remaining.items() if m >= MIN_BLOCK and t not in used_today]
            if not avail:
                break
            t = max(avail, key=lambda x: (remaining[x], needs[x]))
            minutes = min(BLOCK, remaining[t], room)
            if remaining[t] - minutes < MIN_BLOCK:  # absorb a small remainder rather than leave a stub
                minutes = min(remaining[t], room)
            first = t not in seen
            blocks.append({
                "type": "learn" if first else "practice", "topic": t, "name": names[t], "minutes": int(minutes),
                "note": ("Read the Microsoft Learn module, then drill questions on this topic." if first
                         else "Recall first, then 6-8 questions. Fix anything you miss."),
            })
            seen.add(t)
            used_today.add(t)
            remaining[t] -= minutes
            room -= minutes

    days_out = []
    for d in slots:
        blocks = schedule[d]
        days_out.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "days_to_exam": (exam - d).days,
            "minutes": sum(b["minutes"] for b in blocks),
            "blocks": blocks,
        })
    leftover = sum(m for m in remaining.values() if m >= MIN_BLOCK)

    by_topic: dict[str, int] = {}
    for dd in days_out:
        for b in dd["blocks"]:
            if b["type"] in ("learn", "practice"):
                by_topic[b["topic"]] = by_topic.get(b["topic"], 0) + b["minutes"]
    focus = [{"topic": t, "name": names[t], "minutes": m, "score": scores[t]}
             for t, m in sorted(by_topic.items(), key=lambda kv: kv[1], reverse=True)]

    warnings = []
    o = report["overall"]
    if o["answered"] == 0:
        warnings.append("You have not practised yet, so this plan spreads time by exam weight. It will re-balance once you have data: regenerate it after a few sessions.")
    if len(slots) < 4:
        warnings.append("That is very little runway. Consider moving the exam date back if you can.")
    if o["answered"] > 0 and hours_per_week < 3 and (exam - today).days < 21:
        warnings.append("With under 3 hours a week and less than 3 weeks left, aim for the biggest-win topics first.")
    if leftover >= 30:  # smaller gaps are rounding noise
        warnings.append(f"About {leftover} minutes of suggested study did not fit your schedule. Add a study day or an hour a week if you can.")

    total = sum(d["minutes"] for d in days_out)
    return {
        "today": today.isoformat(),
        "exam": exam.isoformat(),
        "days_to_exam": (exam - today).days,
        "hours_per_week": hours_per_week,
        "study_days": days_set,
        "total_minutes": total,
        "study_day_count": len(days_out),
        "mock_dates": [d.isoformat() for d in mock_days],
        "focus": focus,
        "warnings": warnings,
        "days": days_out,
    }
