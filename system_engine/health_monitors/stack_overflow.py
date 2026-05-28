"""Stack Overflow health monitor.

Monitors Stack Overflow for high-vote questions and answers about
libraries used in the system — new bugs, deprecation notices, and
breaking changes surface here before they hit production.

Watched tags by default:
    ``"python"``, ``"numpy"``, ``"pytorch"``, ``"rust"``,
    ``"asyncio"``, ``"kafka"``, ``"redis"``

The base class is a no-op stub; subclasses override ``_fetch_questions``
to activate real Stack Exchange API calls.
"""

from __future__ import annotations

_DEFAULT_TAGS: tuple[str, ...] = (
    "python",
    "numpy",
    "pytorch",
    "rust",
    "asyncio",
    "kafka",
    "redis",
)


class StackOverflowMonitor:
    """Monitors Stack Overflow for high-vote questions about watched libraries.

    The base class keeps the network boundary explicit: no HTTP calls are
    made in ``__init__`` or ``check``. Subclasses override
    ``_fetch_questions`` to activate real Stack Exchange API fetching.
    """

    name: str = "stack_overflow_monitor"
    spec_id: str = "SYS-HEALTH-SOF-01"

    __slots__ = ("_watched_tags", "_last_check_ts_ns", "_flagged_questions")

    def __init__(
        self,
        watched_tags: tuple[str, ...] | None = None,
    ) -> None:
        self._watched_tags: tuple[str, ...] = (
            watched_tags if watched_tags is not None else _DEFAULT_TAGS
        )
        self._last_check_ts_ns: int = 0
        # key: question_id (str) → question dict
        self._flagged_questions: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Fetch hook (override in subclasses / tests)
    # ------------------------------------------------------------------

    def _fetch_questions(self, tag: str) -> list[dict]:
        """Fetch recently flagged high-vote questions for a single tag.

        Base implementation is a no-op returning an empty list. Override
        this method to activate real Stack Exchange API calls.

        Returns a list of question dicts, each with at least:
            * ``"question_id"`` — stable integer or string identifier
            * ``"title"``       — question title
            * ``"score"``       — net vote score
            * ``"tags"``        — list of tag strings
            * ``"link"``        — HTML URL of the question
            * ``"creation_date"`` — Unix timestamp of creation
        """
        return []

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check(self, ts_ns: int) -> list[dict]:
        """Check all watched tags for newly flagged high-vote questions.

        Runs ``_fetch_questions`` for each watched tag, deduplicates
        against the known set, and accumulates new questions.

        Returns
        -------
        list[dict]
            Newly flagged question dicts not seen in previous checks.
        """
        self._last_check_ts_ns = ts_ns
        newly_flagged: list[dict] = []

        for tag in self._watched_tags:
            questions = self._fetch_questions(tag)
            for q in questions:
                qid = str(q.get("question_id", ""))
                if not qid:
                    continue
                if qid not in self._flagged_questions:
                    enriched = dict(q)
                    enriched["flagged_ts_ns"] = ts_ns
                    enriched["flagged_via_tag"] = tag
                    self._flagged_questions[qid] = enriched
                    newly_flagged.append(enriched)

        return newly_flagged

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a serialisable snapshot of monitor state."""
        return {
            "watched_tags": list(self._watched_tags),
            "last_check_ts_ns": self._last_check_ts_ns,
            "flagged_question_count": len(self._flagged_questions),
            "flagged_questions": {
                qid: dict(info) for qid, info in self._flagged_questions.items()
            },
        }


__all__ = ["StackOverflowMonitor"]
