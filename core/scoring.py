"""TEOS Sovereign Video Engine — Predictive Visibility Scoring.

A heuristic forecast of how a short-form video will perform once published,
computed entirely on-device from the script, its spoken pacing and the
richness of matched Sovereign Media Vault visuals. Evidence before publish —
predict before you post.
"""

import re

_OPTIMAL_WORDS = (100, 150)
_TARGET_WPM = (130.0, 150.0)

# Strong short-form openers: questions or pattern-interrupt claims.
_HOOK_MARKERS = (
    "did you know",
    "imagine",
    "the truth",
    "here's the thing",
    "wait until",
    "stop scrolling",
    "everyone's wrong",
    "what if",
    "why",
    "how to",
    "nobody tells you",
    "secret",
    "revealed",
    "warning",
    "biggest mistake",
    "number one",
)

_WEIGHT_LENGTH = 30
_WEIGHT_HOOK = 25
_WEIGHT_PACING = 30
_WEIGHT_VISUALS = 15


def _range_points(value: float, optimal_lo: float, optimal_hi: float, max_points: int) -> int:
    """Full points inside [lo, hi]; linear falloff to zero far outside."""
    if optimal_lo <= value <= optimal_hi:
        return max_points
    if value < optimal_lo:
        return max(0, round(max_points * (1.0 - (optimal_lo - value) / optimal_lo)))
    return max(0, round(max_points * (1.0 - (value - optimal_hi) / optimal_hi)))


def _grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


class VisibilityScorer:
    """Predicts a short-form video's reach/engagement before publishing."""

    def predict_reach(
        self,
        script: str,
        audio_duration: float,
        asset_count: int = 0,
    ) -> dict:
        """Score 0-100 from heuristics.

        Returns a JSON-ready payload with ``score``, ``grade``, ``feedback``
        and the raw ``metrics`` (word count + words-per-minute) behind the call.
        """
        words = re.findall(r"[A-Za-z0-9']+", script or "")
        word_count = len(words)
        wpm = round(word_count / (audio_duration / 60.0), 1) if audio_duration > 0 else 0.0

        feedback: list[str] = []

        length_points = self._length_points(word_count, feedback)
        hook_points = self._hook_points(script, feedback)
        pacing_points = self._pacing_points(wpm, feedback)
        visual_points = self._visual_points(asset_count, feedback)

        score = min(
            100,
            length_points + hook_points + pacing_points + visual_points,
        )
        return {
            "score": score,
            "grade": _grade(score),
            "feedback": feedback,
            "metrics": {"words": word_count, "wpm": wpm},
        }

    def _length_points(self, word_count: int, feedback: list[str]) -> int:
        points = _range_points(word_count, *_OPTIMAL_WORDS, _WEIGHT_LENGTH)
        if _OPTIMAL_WORDS[0] <= word_count <= _OPTIMAL_WORDS[1]:
            feedback.append(f"Script length is ideal ({word_count} words)")
        elif word_count < _OPTIMAL_WORDS[0]:
            feedback.append(
                f"Script is short ({word_count} words) — expand toward 100-150 for retention"
            )
        else:
            feedback.append(
                f"Script is long ({word_count} words) — trim toward 100-150 for completion rate"
            )
        return points

    def _hook_points(self, script: str, feedback: list[str]) -> int:
        first_sentence = re.split(r"[.?!]", script or "", maxsplit=1)[0].strip().lower()
        landed = bool(first_sentence) and (
            any(marker in first_sentence for marker in _HOOK_MARKERS)
            or first_sentence.endswith("?")
            or first_sentence.endswith("!")
        )
        if landed:
            feedback.append("Strong hook — opens with a question or pattern interrupt")
            return _WEIGHT_HOOK
        feedback.append("Lead with a hook — a question or 'Did you know…' opens strong")
        return 0

    def _pacing_points(self, wpm: float, feedback: list[str]) -> int:
        points = _range_points(wpm, *_TARGET_WPM, _WEIGHT_PACING)
        if _TARGET_WPM[0] <= wpm <= _TARGET_WPM[1]:
            feedback.append(f"Pacing is optimal (~{wpm:.0f} WPM)")
        elif wpm == 0:
            feedback.append("Pacing unknown — audio duration was not available")
        elif wpm < _TARGET_WPM[0]:
            feedback.append(f"Pacing is slow ({wpm:.0f} WPM) — tighten for 130-150 WPM")
        else:
            feedback.append(f"Pacing is fast ({wpm:.0f} WPM) — slow to 130-150 WPM for clarity")
        return points

    def _visual_points(self, asset_count: int, feedback: list[str]) -> int:
        points = round(_WEIGHT_VISUALS * min(asset_count, 3) / 3)
        if asset_count > 0:
            feedback.append(
                f"Matched {asset_count} Sovereign Media Vault visual{'s' if asset_count != 1 else ''} — richer frames"
            )
        else:
            feedback.append("No vault visuals matched — the brand canvas carries the frame")
        return points