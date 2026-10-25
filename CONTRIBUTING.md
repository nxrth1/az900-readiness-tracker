# Contributing

The most valuable contribution is **making the questions trustworthy**. A study tool lives or dies on whether
learners can rely on every question being correct and current.

## Ground rules for questions

* **Original only.** Write from the public [AZ-900 study guide](https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-900)
  and Microsoft Learn. Never paste real exam questions, "brain dumps" or text copied from other practice sites.
* **One clear correct answer** and three plausible wrong ones. Avoid trick wording, "all of the above" and negatives
  ("which is NOT...") unless the skill is genuinely about exclusions.
* **Explain every option**: `why` says why the answer is right, `why_not` says why each wrong option is wrong.
* **Map it to exactly one topic** (see `app/questions.py`). If it straddles two, split the question.
* **Ids are permanent.** Never reuse an id for different content; stored answers and backups refer to it.
* Run `python -m app.questions` and `python -m pytest -q` before opening a pull request.

## Reviewing questions (the checklist)

A question is "reviewed" only when a person has checked all of this against the **current** study guide and Learn
module for its topic (`python -m app.review show <id>` prints the question and the page to check against):

1. The stem is accurate and unambiguous, and matches a skill listed in the current outline.
2. Exactly one option is correct, today. Services get renamed (Azure AD became Microsoft Entra ID) and features change.
3. Every wrong option is genuinely wrong, and its `why_not` is true.
4. The `why` is accurate and teaches the idea, not just the answer.
5. The topic mapping and difficulty (1 to 3) are sensible.

Then record it:

```bash
python -m app.review status                    # progress by topic
python -m app.review list --unreviewed --topic compute
python -m app.review show comp-01 comp-02
python -m app.review mark comp-01 comp-02      # asks you to confirm a person checked them
```

Commit `app/data/question_review.json` and **name the reviewer in the commit or pull request**. Editing a question
after it was reviewed? Run `python -m app.review unmark <id>` so it goes back to unchecked.

## When Microsoft updates the exam

1. Read the "Skills measured" and change-log sections of the study guide.
2. Update `skills_measured_as_of` in `app/data/learn_links.json` and `app/data/question_review.json`.
3. Re-check the Learn links (`python -m app.learn` validates their shape; open them to confirm they still resolve).
4. Unmark every question whose skill changed, and add questions for new skills.

## Code changes

`ruff check .` and `python -m pytest --cov=app` must pass (CI runs both, plus an end-to-end browser-engine smoke test
in `e2e/`). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit.
