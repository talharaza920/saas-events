"""The guests ask-back round (AI_WIZARD_PLAN Phase 8.5c).

A pasted guest list is the one submission that is routinely, genuinely
ambiguous: "Sam's parents", "the Chens (4?)", "Priya + fam". The model's two bad
options are to guess (and invent people) or to drop the line (and lose them).
The third option is the one a person would take: ask.

    extract ─▶ awaiting_review  (partial list + a few questions)
                     │
              couple answers inline
                     │
                     ▼
              ONE re-extract  ─▶ awaiting_review (final list)

Four rules keep this a workflow rather than a chat:

1. **Two rounds, hard cap.** The re-run is `final`, so it cannot ask again.
   Whatever it still can't place is left in `guests_unresolved` for the couple
   to add by hand. An assistant that can keep asking is an assistant that can
   keep spending.
2. **Answering is free.** We ask because our extraction was uncertain; charging
   a credit to answer our own question is charging the couple for our doubt. The
   ledger still records the call's true dollar cost — the round cap is the spend
   bound, not a price.
3. **The answers are just more submission.** They land as an ordinary `AiInput`
   row (swept with the job like every other raw submission) and are appended to
   the transcript inside `<clarifications>` tags — untrusted data, exactly like
   the paste they clarify.
4. **Tiers stay in code.** The questions are about WHO is on a line. `+1` and
   kid markers are read by `guest_import.infer_tier`, never by the model, and no
   answer here can reach an `invite_tier` (guardrail 1).

A failed re-run costs the couple nothing and destroys nothing: the partial list
from round one is still sitting in the proposal, still applicable.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.jobs import build_proposal, check_circuit_breaker, run_guests_step
from app.ai.media import MAX_TRANSCRIPT_CHARS
from app.ai.types import ProviderError, ProviderRefusal, TextModel
from app.audit_log import record
from app.config import Settings
from app.models import AiInput, AiJob, AiJobKind, AiJobStatus
from app.obs import log_event

logger = logging.getLogger("app.ai")

# The extraction round the couple got, plus the one their answers buy.
MAX_ROUNDS = 2
MAX_ANSWER_CHARS = 200


def answer_questions(
    db: Session,
    settings: Settings,
    job: AiJob,
    *,
    answers: list[dict],
    text_model: TextModel,
    user=None,
) -> AiJob:
    """Answer the open questions on a `guests` proposal and re-extract ONCE.

    `answers` are `{index, answer}` against the proposal's own `questions` list;
    a blank or missing answer is simply an unanswered question, and its line ends
    up unresolved rather than guessed at. Raises 409 (not in review), 422 (wrong
    kind / nothing asked / rounds spent / unknown index / re-read failed), 503
    (breaker). Commits.
    """
    if job.kind != AiJobKind.GUESTS:
        raise HTTPException(status_code=422, detail="Only a guest-list run asks questions")
    if job.status != AiJobStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}")

    proposal = dict(job.proposal or {})
    questions = [q for q in (proposal.get("questions") or []) if isinstance(q, dict)]
    if not questions:
        raise HTTPException(status_code=422, detail="There's nothing left to clear up")
    rounds = int((job.state or {}).get("guest_rounds") or 0)
    if rounds >= MAX_ROUNDS:
        raise HTTPException(
            status_code=422,
            detail="We've already had one go at this — add anyone still missing from the Guests tab",
        )

    answered: list[tuple[dict, str]] = []
    for item in answers:
        idx = item.get("index")
        if not isinstance(idx, int) or not 0 <= idx < len(questions):
            raise HTTPException(status_code=422, detail="That question isn't on this run")
        text = (item.get("answer") or "").strip()[:MAX_ANSWER_CHARS]
        if text:
            answered.append((questions[idx], text))
    if not answered:
        raise HTTPException(status_code=422, detail="Answer at least one question first")

    check_circuit_breaker(db)

    block = "\n".join(
        f"- {q.get('about_line', '')} — {q.get('question', '')} → {text}" for q, text in answered
    )
    # Work on a COPY: if the re-read fails, round one's list is untouched and
    # still applicable. Nothing here is destructive.
    state = dict(job.state or {})
    state["submission"] = (
        f"{state.get('submission', '')}\n\n<clarifications>\n{block}\n</clarifications>"
    )[:MAX_TRANSCRIPT_CHARS]

    try:
        run_guests_step(db, settings, job, state, text_model, final=True)
    except (ProviderError, ProviderRefusal) as exc:
        # The ledger rows for a call that actually ran are staged in this
        # session; commit them (the money moved, so the books say so) and leave
        # the job exactly as the couple found it.
        db.commit()
        log_event(logger, "ai.job.askback.failed", job_id=str(job.id), error=str(exc)[:200])
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't re-read your list ({exc}) — the list you already have is still fine to apply",
        ) from exc

    # An unanswered question is not a failure: its line just stays unresolved,
    # which is the honest outcome — better a name the couple adds by hand than a
    # party we invented for them.
    answered_lines = {q.get("about_line") for q, _ in answered}
    unresolved = list(state.get("guests_unresolved") or [])
    for q in questions:
        line = q.get("about_line")
        if line and line not in answered_lines and line not in unresolved:
            unresolved.append(line)
    state["guests_unresolved"] = unresolved

    db.add(
        AiInput(
            wedding_id=job.wedding_id,
            job_id=job.id,
            kind="text",
            text_content=block,
            bytes=len(block.encode("utf-8")),
            created_by=getattr(user, "sub", None),
        )
    )
    job.state = state  # reassign: JSON columns don't track in-place mutation
    job.proposal = build_proposal(job)
    record(
        db, "ai.job.answers", user=user, wedding=job.wedding,
        target_type="ai_job", target_id=job.id,
        detail={"answered": len(answered), "asked": len(questions), "round": rounds + 1},
    )
    db.commit()
    db.refresh(job)
    return job
