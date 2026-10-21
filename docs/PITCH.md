# Pitch kit: AZ-900 Readiness Tracker

Everything here maps to the hackathon's pitch criteria. Items in **[brackets]** are for you to fill in, because they depend on your own AZ-900 experience.

## Submission checklist (deadline Fri 23 Oct, 6:00 PM EAT)

- [ ] Push this repo to GitHub (public), add the repo link to the submission form
- [ ] Deploy a working demo (see README, Docker section) or record a 2-3 minute screen capture as the fallback
- [ ] Read through the question bank against Microsoft Learn (accuracy is 25% of the judging)
- [ ] Run the 10-question Claude explanation check in `docs/PROMPTS.md` and record results
- [ ] Fill the Canva template using the slide plan below
- [ ] Confirm: "Unofficial" label visible, no Microsoft logos, no copied exam questions

## One-line pitch

> **"Most learners finish a practice test with a score and no idea whether to book the exam. Readiness Tracker turns every answer into an honest estimate, with error bars, and tells you the three things that would raise it most."**

## Slide plan (8 slides)

| # | Slide | Criterion it earns | Content |
|---|---|---|---|
| 1 | Title | Clarity | Name, one-line pitch, "Unofficial AZ-900 study tool" |
| 2 | The problem | Problem Understanding (20%) | **[Your story: when did you not know if you were ready? What did you wish you had?]** Practice tests give one number, no confidence, no direction. |
| 3 | The solution | Solution & Product (25%) | Dashboard screenshot: estimated score with likely range, domain bars, topic map, biggest wins |
| 4 | Live demo | Solution & Product | See demo script below |
| 5 | How it works | Technical creativity | Bayesian topic estimates, guess vs sure, forgetting curve, exam-weighted roll-up, pass likelihood. One diagram, no maths wall |
| 6 | Who it is for | Target Users (15%) | First-time AZ-900 candidates (students, career switchers), study groups and community leads, bootcamps and 1M Devs cohort mentors |
| 7 | Impact and scale | Impact & Scalability (20%) | Data-driven design: swap the skills outline and question file for AZ-104, AWS Cloud Practitioner, GCP. Instructor cohort heatmap. Works offline and on low bandwidth (no build step, tiny page). Kiswahili explanations |
| 8 | Ask / next steps | Clarity, Design & Delivery | Roadmap: exam-date planner, Supabase sync, more certifications. Repo and demo links |

## 3-minute demo script

1. **(0:00)** Open an empty dashboard. "This is what a new learner sees. No number yet, because we refuse to guess."
2. **(0:20)** Click **Load demo data** ("ten days of practice"). Gauge appears. Point at: estimate, likely range, pass line, "about a 4% chance on today's evidence".
3. **(0:50)** Domain bars. "Weighted like the real exam. The grey bar is uncertainty, not decoration."
4. **(1:10)** **Biggest wins.** "It does not say 'study more'. It says: Cost management, 2.6 points available. And these are topics where you were *sure* but wrong, the dangerous kind."
5. **(1:35)** Click a weak tile or **Smart review**. Answer a question, flip **I'm just guessing** on one, then check. "Guesses count for half. Honest data in, honest score out."
6. **(2:10)** On a wrong answer: curated "why your option is wrong" appears instantly. Click **Explain it simply**, switch to **Kiswahili**. "Claude re-explains using the curated explanation as ground truth, so it adds clarity, not new facts." (Needs an API key configured.)
6b. **(2:25)** Open **Plan**, enter an exam date three weeks out. "Same engine, now as a schedule: weak topics get the time, a mock exam lands a week out, the last day is light."
7. **(2:40)** Finish the session. Results show the change in estimated score. "Learners see progress in points, not vibes."
8. **(2:55)** Close on the one-liner.

## Anticipated judge questions

- **"Is the score accurate?"** It is a calibrated estimate, not a prediction. We show the range and say so on screen. Real exam scaling (700/1000) is approximated as 70%.
- **"Where do the questions come from?"** Written from the public skills outline, original, each with a reason every wrong option is wrong. No exam dumps.
- **"Why not let AI generate the questions?"** Accuracy. Claude only explains, grounded in vetted content. Grading and scoring are deterministic and tested (64 tests).
- **"What if the API key is missing or Claude fails?"** Everything works; curated explanations are always shown first.
- **"How does it scale?"** Domains/topics are data. Add a question file and weights for a new certification. SQLite to Postgres is a connection change.
- **"What did you build in the time?"** Backend, scoring engine, adaptive selection, mock exam, dashboard, tests, CI, Docker, docs.

## Score mapping to judging criteria

| Criterion | Where to point |
|---|---|
| Learning Value (25%) | 64 original questions with per-option explanations; misconception detection; "biggest wins" |
| Prompt Engineering (20%) | `docs/PROMPTS.md`: grounded, structured, bounded, bilingual; cache and fallback |
| UX and Vibes (15%) | Gauge with uncertainty, topic heat map, keyboard support, light and dark, mobile-safe |
| Rapid Prototyping (15%) | Working end to end with tests; built with Claude |
| Technical Creativity (15%) | Beta-posterior estimates with recency decay; guess-aware evidence; pass likelihood |
| Presentation and Docs (10%) | README, screenshots, architecture, API table, CI |
