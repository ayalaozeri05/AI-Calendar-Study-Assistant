"""AI study planning — deterministic schedule + optional LLM content polish."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from typing import Any

from app.config import settings
from app.gateways.ollama_gateway import (
    OllamaError,
    OllamaGateway,
    OllamaTimeoutError,
    save_raw_ollama_response,
)
from app.rag.document_matcher import course_lookup_key, normalize_key
from app.rag.rag_service import RagService
from app.schemas.brief_schema import PriorityItem, StructuredStudyPlan
from app.schemas.calendar_schema import ClassifiedCalendarEvent, EventCategory
from app.services.study_scheduling_engine import StudySchedulingEngine, plan_fingerprint

logger = logging.getLogger(__name__)

_PRIORITY = (
    EventCategory.EXAM,
    EventCategory.ASSIGNMENT,
    EventCategory.PROJECT,
    EventCategory.STUDY,
    EventCategory.CLASS,
    EventCategory.MEETING,
    EventCategory.OTHER,
)


class AiRecommendationService:
    def __init__(
        self,
        ollama: OllamaGateway | None = None,
        engine: StudySchedulingEngine | None = None,
        rag: RagService | None = None,
    ) -> None:
        self._ollama = ollama or OllamaGateway()
        self._engine = engine or StudySchedulingEngine()
        self._rag = rag or RagService()
        # Last polish outcome for API meta / debugging (not secrets).
        self.last_fallback_reason: str | None = None
        self.last_ollama_answered: bool | None = None
        self.last_ollama_elapsed_sec: float | None = None
        self.last_ollama_called: bool = False
        self.last_rag_used: bool = False
        self.last_rag_topic_count: int = 0
        self.last_rag_message: str | None = None
        self.last_rag_topics: list[str] = []
        self.last_rag_chunk_count: int = 0
        self.last_rag_document: str | None = None
        self.last_rag_matched_documents: list[str] = []
        self.last_rag_match_reason: str | None = None

    def suggest_focus(self, events: list[ClassifiedCalendarEvent]) -> str:
        plan, _, _, _ = self.generate_study_plan(
            events,
            start=datetime.now(timezone.utc).date(),
            end=datetime.now(timezone.utc).date(),
            force_fallback=True,
        )
        if plan.priority_item:
            return f"{plan.priority_item.title}: {plan.priority_item.reason}".strip(": ")
        if plan.tips:
            return plan.tips[0]
        return plan.summary or "Review your schedule and start with the earliest item."

    def generate_study_plan(
        self,
        events: list[ClassifiedCalendarEvent],
        *,
        start: date,
        end: date,
        force_fallback: bool = False,
        now: datetime | None = None,
        regenerate: bool = False,
        previous_plan: dict[str, Any] | None = None,
        variation_seed: int | None = None,
        planning_anchor: datetime | str | None = None,
    ) -> tuple[StructuredStudyPlan, str, str, list[str]]:
        language = detect_language(events)
        now = now or datetime.now().astimezone()
        seed = int(variation_seed or 0)
        if regenerate and seed == 0:
            seed = int(now.timestamp()) % 10_000_000
        warnings: list[str] = []

        anchor_dt = _parse_anchor(planning_anchor)
        if regenerate and anchor_dt is None and previous_plan:
            anchor_dt = _parse_anchor(
                (previous_plan or {}).get("planning_anchor")
            )

        # Silent RAG enrichment: improve WHAT to study when a PDF is indexed.
        # Never blocks plan generation if embeddings/Chroma are unavailable.
        rag_topics = self._collect_rag_topics(events)

        t0 = time.perf_counter()
        plan = self._engine.build(
            events,
            range_start=start,
            range_end=end,
            now=now,
            language=language,
            variation_seed=seed,
            planning_anchor=anchor_dt,
            rag_topics=rag_topics or None,
        )
        logger.info(
            "stage=deterministic_schedule_completed duration_ms=%.0f "
            "event_count=%s day_count=%s block_count=%s rag_used=%s",
            (time.perf_counter() - t0) * 1000,
            len(events),
            len(plan.daily_plan or []),
            sum(len(d.items) for d in (plan.daily_plan or [])),
            bool(rag_topics),
        )

        # If regenerate produced an identical skeleton, retry once with stronger seed
        if regenerate and previous_plan:
            try:
                prev = StructuredStudyPlan.model_validate(previous_plan)
                if plan_fingerprint(plan) == plan_fingerprint(prev):
                    plan = self._engine.build(
                        events,
                        range_start=start,
                        range_end=end,
                        now=now,
                        language=language,
                        variation_seed=seed + 7919,
                        planning_anchor=anchor_dt or _parse_anchor(plan.planning_anchor),
                        rag_topics=rag_topics or None,
                    )
            except Exception:
                pass

        engine_plan = plan
        ai_mode = "deterministic"
        fallback_reason: str | None = None
        self.last_fallback_reason = None
        self.last_ollama_answered = None
        self.last_ollama_elapsed_sec = None
        self.last_ollama_called = False
        # Source of truth: AI_POLISH_ENABLED. SKIP_OLLAMA_POLISH is deprecated override.
        polish_on = bool(getattr(settings, "polish_enabled", False)) and not force_fallback

        if not polish_on:
            # Intentional stable/demo path — not a failure.
            ai_mode = "deterministic"
            fallback_reason = None
            logger.info(
                "stage=ollama_polish_disabled ai_mode=deterministic "
                "ai_polish_enabled=%s skip_ollama_polish=%s force_fallback=%s "
                "day_count=%s block_count=%s",
                bool(getattr(settings, "ai_polish_enabled", False)),
                bool(getattr(settings, "skip_ollama_polish", False)),
                force_fallback,
                len(plan.daily_plan or []),
                sum(len(d.items) for d in (plan.daily_plan or [])),
            )
        else:
            budget = max(5.0, float(getattr(settings, "ollama_timeout_sec", 75.0) or 75.0))
            deadline = time.perf_counter() + budget
            try:
                t_avail = time.perf_counter()
                available = self._ollama.is_available()
                logger.info(
                    "stage=ollama_availability duration_ms=%.0f available=%s "
                    "total_budget_sec=%.0f",
                    (time.perf_counter() - t_avail) * 1000,
                    available,
                    budget,
                )
                if available:
                    self.last_ollama_called = True
                    remaining = deadline - time.perf_counter()
                    if remaining < 5.0:
                        raise OllamaTimeoutError(
                            "Ollama polish budget exhausted before invoke.",
                            reason="timeout",
                        )
                    t_ollama = time.perf_counter()
                    logger.info(
                        "stage=ollama_call_started remaining_budget_sec=%.1f "
                        "day_count=%s block_count=%s",
                        remaining,
                        len(plan.daily_plan or []),
                        sum(len(d.items) for d in (plan.daily_plan or [])),
                    )
                    plan = self._polish_with_ollama(
                        plan,
                        events,
                        language=language,
                        regenerate=regenerate,
                        previous_plan=previous_plan,
                        deadline=deadline,
                    )
                    ai_mode = "ollama"
                    self.last_ollama_answered = True
                    self.last_ollama_elapsed_sec = time.perf_counter() - t_ollama
                    logger.info(
                        "stage=ollama_call_completed duration_ms=%.0f ai_mode=ollama",
                        (self.last_ollama_elapsed_sec or 0.0) * 1000,
                    )
                else:
                    fallback_reason = "ollama_unavailable"
                    ai_mode = "rule_based_fallback"
                    logger.warning(
                        "fallback_reason=%s model=%s keeping_engine_plan",
                        fallback_reason,
                        self._ollama.model or "(unset)",
                    )
            except OllamaTimeoutError as exc:
                plan = engine_plan
                ai_mode = "rule_based_fallback"
                fallback_reason = getattr(exc, "reason", None) or "timeout"
                elapsed = time.perf_counter() - (deadline - budget)
                self.last_ollama_answered = False
                self.last_ollama_elapsed_sec = elapsed
                logger.warning(
                    "fallback_reason=%s stage=ollama_polish_timeout elapsed=%.1f "
                    "fallback_returned=true err=%s",
                    fallback_reason,
                    elapsed,
                    type(exc).__name__,
                )
                # Technical only — desktop normal UI must not surface this.
            except OllamaError as exc:
                plan = engine_plan
                ai_mode = "rule_based_fallback"
                fallback_reason = getattr(exc, "reason", None) or "http_error"
                self.last_ollama_answered = False
                logger.warning(
                    "fallback_reason=%s keeping_engine_plan err=%s detail=%s",
                    fallback_reason,
                    type(exc).__name__,
                    exc,
                )
            except Exception as exc:
                plan = engine_plan
                ai_mode = "rule_based_fallback"
                fallback_reason = "parser_exception"
                self.last_ollama_answered = False
                logger.warning(
                    "fallback_reason=%s keeping_engine_plan err=%s detail=%s",
                    fallback_reason,
                    type(exc).__name__,
                    exc,
                )

        day_count = len(plan.daily_plan or [])
        block_count = sum(len(d.items) for d in (plan.daily_plan or []))
        if day_count <= 0 or block_count <= 0:
            fallback_reason = fallback_reason or "empty_plan_guard"
            logger.warning(
                "fallback_reason=%s stage=empty_plan_guard day_count=%s block_count=%s — "
                "returning engine plan",
                fallback_reason,
                day_count,
                block_count,
            )
            plan = engine_plan
            ai_mode = "rule_based_fallback"

        if ai_mode == "rule_based_fallback":
            self.last_fallback_reason = fallback_reason or "rule_based_fallback"
            logger.info(
                "fallback_reason=%s ai_mode=%s",
                self.last_fallback_reason,
                ai_mode,
            )
        else:
            # deterministic / ollama — intentional success paths
            self.last_fallback_reason = None

        # Guarantee retrieved topics appear in study actions (even if polish
        # rewrote wording, or id-keyed lookup missed during scheduling).
        plan = self._apply_rag_topics_to_actions(plan, rag_topics, events)

        return plan, format_plan_text(plan, language=language), ai_mode, warnings

    def _collect_rag_topics(
        self,
        events: list[ClassifiedCalendarEvent],
    ) -> dict[str, list[str]]:
        """Retrieve study topics from uploaded PDF material when available."""
        self.last_rag_used = False
        self.last_rag_topic_count = 0
        self.last_rag_message = None
        self.last_rag_topics = []
        self.last_rag_chunk_count = 0
        self.last_rag_document = None
        self.last_rag_matched_documents = []
        self.last_rag_match_reason = None
        try:
            topics = self._rag.topics_for_events(events)
        except Exception as exc:
            logger.info(
                "rag_enrichment_skipped reason=%s",
                type(exc).__name__,
            )
            if self._rag.has_indexed_material():
                self.last_rag_message = (
                    "No relevant study material was found for this study plan."
                )
            return {}
        self.last_rag_document = getattr(self._rag, "last_matched_document", None)
        self.last_rag_matched_documents = list(
            getattr(self._rag, "last_matched_documents", []) or []
        )
        if not self.last_rag_matched_documents and self.last_rag_document:
            self.last_rag_matched_documents = [self.last_rag_document]
        self.last_rag_match_reason = getattr(self._rag, "last_match_reason", None)
        self.last_rag_chunk_count = int(
            getattr(self._rag, "last_chunk_count", 0) or 0
        )
        self.last_rag_topics = list(getattr(self._rag, "last_topics", []) or [])
        if topics:
            # Count unique topic lists (event id + course: key share values).
            seen: set[tuple[str, ...]] = set()
            total = 0
            flat: list[str] = []
            for values in topics.values():
                key = tuple(values)
                if key in seen:
                    continue
                seen.add(key)
                total += len(values)
                flat.extend(values)
            self.last_rag_topic_count = total
            if not self.last_rag_topics:
                self.last_rag_topics = flat
            logger.info(
                "stage=rag_topics_collected events_with_topics=%s topic_count=%s "
                "matched_documents=%s retrieved_chunks=%s",
                len(topics),
                self.last_rag_topic_count,
                self.last_rag_matched_documents,
                self.last_rag_chunk_count,
            )
        elif self._rag.has_indexed_material():
            self.last_rag_message = (
                "No relevant study material was found for this study plan."
            )
        return topics

    def _apply_rag_topics_to_actions(
        self,
        plan: StructuredStudyPlan,
        rag_topics: dict[str, list[str]],
        events: list[ClassifiedCalendarEvent],
    ) -> StructuredStudyPlan:
        """Inject / verify RAG topics in study actions; set last_rag_used honestly."""
        self.last_rag_used = False
        if not rag_topics:
            logger.info(
                "stage=rag_retrieval matched_documents=%s retrieved_chunks=%s "
                "topics=[] rag_used=false",
                getattr(self, "last_rag_matched_documents", []) or [],
                int(getattr(self, "last_rag_chunk_count", 0) or 0),
            )
            return plan

        by_course = _topics_by_course_key(rag_topics, events)
        topic_values = [t for topics in by_course.values() for t in topics]

        actions_after: list[str] = []
        changed = False
        for day in plan.daily_plan or []:
            for item in day.items:
                if (item.kind or "") != "study":
                    continue
                topics = _match_topics_for_title(item.title or "", by_course)
                if not topics:
                    if item.action:
                        actions_after.append(item.action)
                    continue
                action = (item.action or "").strip()
                action_cf = action.casefold()
                if any(t.casefold() in action_cf for t in topics):
                    actions_after.append(action)
                    continue
                # Force concrete topics into the action line.
                bundle = ", ".join(topics[:4])
                item.action = f"Study: {bundle}"
                changed = True
                actions_after.append(item.action)

        verified = any(
            any(t.casefold() in (a or "").casefold() for t in topic_values)
            for a in actions_after
        )
        if verified:
            self.last_rag_used = True
            self.last_rag_message = None
            logger.info(
                "stage=rag_retrieval matched_documents=%s retrieved_chunks=%s "
                "topics=%s rag_used=true",
                getattr(self, "last_rag_matched_documents", []) or [],
                int(getattr(self, "last_rag_chunk_count", 0) or 0),
                list(dict.fromkeys(topic_values))[:12],
            )
        else:
            self.last_rag_used = False
            if self._rag.has_indexed_material():
                self.last_rag_message = (
                    "No relevant study material was found for this study plan."
                )
            logger.info(
                "stage=rag_retrieval matched_documents=%s retrieved_chunks=%s "
                "topics=%s rag_used=false reason=topics_missing_in_actions",
                getattr(self, "last_rag_matched_documents", []) or [],
                int(getattr(self, "last_rag_chunk_count", 0) or 0),
                list(dict.fromkeys(topic_values))[:12],
            )
        _ = changed
        return plan

    def _polish_with_ollama(
        self,
        plan: StructuredStudyPlan,
        events: list[ClassifiedCalendarEvent],
        *,
        language: str,
        regenerate: bool,
        previous_plan: dict[str, Any] | None,
        deadline: float | None = None,
    ) -> StructuredStudyPlan:
        # events / previous_plan intentionally unused in wording-only polish.
        _ = events, previous_plan

        wording_bundle, slot_map = _extract_wording_bundle(plan)
        prompt = _build_wording_polish_prompt(
            wording_bundle,
            language=language,
            regenerate=regenerate,
        )
        # Size comparison vs legacy full-schedule prompt (not sent).
        legacy_chars = len(
            _build_legacy_full_schedule_prompt(
                plan, events, language=language, regenerate=regenerate
            )
        )

        def _remaining() -> float:
            if deadline is None:
                return float(getattr(settings, "ollama_timeout_sec", 75.0) or 75.0)
            return deadline - time.perf_counter()

        remaining = _remaining()
        if remaining < 5.0:
            raise OllamaTimeoutError(
                "Ollama polish budget exhausted before first invoke.",
                reason="timeout",
            )

        temperature = 0.35 if regenerate else 0.25
        # Bound generation — wording JSON is small.
        max_tokens = 700
        logger.info(
            "stage=ollama_polish_prompt design=wording_only "
            "prompt_chars_before=%s prompt_chars_after=%s "
            "wording_items=%s language=%s temperature=%s max_tokens=%s "
            "remaining_budget_sec=%.1f",
            legacy_chars,
            len(prompt),
            len(wording_bundle.get("items") or []),
            language,
            temperature,
            max_tokens,
            remaining,
        )

        t_invoke = time.perf_counter()
        raw = self._ollama.invoke(
            prompt,
            temperature=temperature,
            timeout_sec=remaining,
            max_tokens=max_tokens,
        )
        invoke_elapsed = time.perf_counter() - t_invoke
        self.last_ollama_elapsed_sec = invoke_elapsed
        self.last_ollama_answered = True
        logger.info(
            "stage=ollama_raw_before_parse answered=true elapsed_sec=%.3f "
            "response_chars=%s raw_preview=%r",
            invoke_elapsed,
            len(raw or ""),
            (raw or "")[:500],
        )

        polished, parse_reason = _parse_wording_bundle(raw)
        logger.info(
            "stage=ollama_parse json_ok=%s schema_ok=%s parse_reason=%s",
            parse_reason not in {"invalid_json", "empty_response"},
            parse_reason == "ok",
            parse_reason,
        )
        if polished is None:
            save_raw_ollama_response(raw, note=f"parse_failed reason={parse_reason}")
            remaining = _remaining()
            if remaining < 5.0:
                raise OllamaTimeoutError(
                    "Ollama polish budget exhausted; skipping JSON retry.",
                    reason="timeout",
                )
            raw2 = self._ollama.invoke(
                "Return ONLY valid JSON with keys summary, priority_reason, tips, items. "
                "No markdown.\n\n"
                f"Previous reply:\n{raw[:1200]}",
                temperature=0.0,
                timeout_sec=remaining,
                max_tokens=max_tokens,
            )
            logger.info(
                "stage=ollama_raw_retry_before_parse response_chars=%s raw_preview=%r",
                len(raw2 or ""),
                (raw2 or "")[:500],
            )
            polished, parse_reason = _parse_wording_bundle(raw2)
            logger.info(
                "stage=ollama_parse_retry json_ok=%s schema_ok=%s parse_reason=%s",
                parse_reason not in {"invalid_json", "empty_response"},
                parse_reason == "ok",
                parse_reason,
            )
            if polished is None:
                save_raw_ollama_response(
                    raw2, note=f"parse_retry_failed reason={parse_reason}"
                )
                raise OllamaError(
                    f"Model did not return valid wording JSON ({parse_reason}).",
                    reason=parse_reason,
                )

        logger.info(
            "stage=ollama_polish_metrics prompt_chars_before=%s prompt_chars_after=%s "
            "ollama_elapsed_sec=%.3f ai_mode_candidate=ollama",
            legacy_chars,
            len(prompt),
            invoke_elapsed,
        )
        return _apply_wording_bundle(plan, polished, slot_map)


def _extract_wording_bundle(
    plan: StructuredStudyPlan,
) -> tuple[dict[str, Any], list[tuple[int, int]]]:
    """Pull only NL fields. Engine keeps times/dates/order/kinds/titles."""
    items: list[dict[str, str]] = []
    slot_map: list[tuple[int, int]] = []
    for day_idx, day in enumerate(plan.daily_plan or []):
        for item_idx, item in enumerate(day.items or []):
            kind = (item.kind or "study").lower()
            # Wording targets: study / recovery / phase text. Skip pure structure blocks.
            if kind in {"break", "meal", "calendar"}:
                continue
            action = (item.action or "").strip()
            reason = (item.reason or "").strip()
            phase = (item.phase or item.label or "").strip()
            if not (action or reason or phase):
                continue
            slot_map.append((day_idx, item_idx))
            row: dict[str, str] = {}
            if action:
                row["action"] = action
            if reason:
                row["reason"] = reason
            if phase:
                row["phase"] = phase
            items.append(row)

    # Cap polish volume so the model finishes quickly.
    max_items = 16
    if len(items) > max_items:
        items = items[:max_items]
        slot_map = slot_map[:max_items]

    bundle: dict[str, Any] = {
        "summary": (plan.summary or "").strip(),
        "tips": [t.strip() for t in (plan.tips or []) if t and t.strip()][:4],
        "items": items,
    }
    if plan.priority_item and (plan.priority_item.reason or "").strip():
        bundle["priority_reason"] = plan.priority_item.reason.strip()
    return bundle, slot_map


def _build_wording_polish_prompt(
    wording_bundle: dict[str, Any],
    *,
    language: str,
    regenerate: bool,
) -> str:
    lang_rule = (
        "Write EVERY string in Hebrew. Course names may stay as-is."
        if language == "he"
        else "Write EVERY string in English. Course names may stay as-is."
    )
    regen = (
        "Vary the wording meaningfully from the drafts, but keep the same meaning and item count/order."
        if regenerate
        else "Improve clarity and specificity; keep the same item count and order."
    )
    payload = json.dumps(wording_bundle, ensure_ascii=False, separators=(",", ":"))
    return f"""You are an academic writing assistant.
{lang_rule}
{regen}

Improve ONLY the natural-language study coaching text below.
Do not invent a schedule. Do not add dates, times, or new items.
Keep the same number of items in the same order.
Return ONLY valid JSON with keys: summary, priority_reason, tips, items.
Each items[i] may have: action, reason, phase.

Draft JSON:
{payload}
""".strip()


def _build_legacy_full_schedule_prompt(
    plan: StructuredStudyPlan,
    events: list[ClassifiedCalendarEvent],
    *,
    language: str,
    regenerate: bool,
) -> str:
    """Previous polish design — used only to measure prompt size reduction."""
    skeleton = _compact_skeleton_for_polish(plan.model_dump())
    lang_rule = "Hebrew." if language == "he" else "English."
    regen = "regenerate" if regenerate else ""
    return (
        f"{lang_rule}\n{regen}\n"
        f"{json.dumps(skeleton, ensure_ascii=False, indent=2)}\n"
        f"{json.dumps(build_event_metadata(events, today=datetime.now().date()), ensure_ascii=False, indent=2)}"
    )


def _compact_skeleton_for_polish(skeleton: dict[str, Any]) -> dict[str, Any]:
    """Legacy helper kept for size-comparison of the old full-schedule prompt."""
    days = list(skeleton.get("daily_plan") or [])
    max_days = 7
    max_items = 12
    compact_days = []
    for day in days[:max_days]:
        items = list(day.get("items") or [])[:max_items]
        compact_days.append({**day, "items": items})
    out = dict(skeleton)
    out["daily_plan"] = compact_days
    if len(days) > max_days:
        out["_note"] = f"Schedule truncated for polish ({len(days)} days total)."
    return out


def _apply_wording_bundle(
    engine_plan: StructuredStudyPlan,
    wording: dict[str, Any],
    slot_map: list[tuple[int, int]],
) -> StructuredStudyPlan:
    """Merge polished NL text back; engine geometry is untouched."""
    summary = str(wording.get("summary") or "").strip()
    if summary:
        engine_plan.summary = summary

    priority_reason = str(wording.get("priority_reason") or "").strip()
    if priority_reason and engine_plan.priority_item:
        engine_plan.priority_item = PriorityItem(
            title=engine_plan.priority_item.title,
            reason=priority_reason,
        )

    tips_raw = wording.get("tips")
    if isinstance(tips_raw, list):
        tips = [str(t).strip() for t in tips_raw if str(t).strip()]
        if tips:
            engine_plan.tips = tips[:4]

    items_raw = wording.get("items")
    if not isinstance(items_raw, list):
        return engine_plan

    for idx, (day_idx, item_idx) in enumerate(slot_map):
        if idx >= len(items_raw):
            break
        if day_idx >= len(engine_plan.daily_plan):
            continue
        day = engine_plan.daily_plan[day_idx]
        if item_idx >= len(day.items):
            continue
        item = day.items[item_idx]
        cand = items_raw[idx]
        if not isinstance(cand, dict):
            continue
        action = str(cand.get("action") or "").strip()
        reason = str(cand.get("reason") or "").strip()
        phase = str(cand.get("phase") or "").strip()
        if action:
            item.action = action
        if reason and (item.kind or "study") == "study":
            item.reason = reason
        elif reason and not item.reason:
            item.reason = reason
        if phase:
            item.phase = phase
    return engine_plan


def _parse_wording_bundle(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = (raw or "").strip()
    if not text:
        return None, "empty_response"
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None, "invalid_json"
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None, "invalid_json"
    if not isinstance(data, dict):
        return None, "unexpected_response_format"
    # Minimal schema: object with at least one polishable key.
    if not any(k in data for k in ("summary", "priority_reason", "tips", "items")):
        return None, "schema_validation_failure"
    if "items" in data and data["items"] is not None and not isinstance(data["items"], list):
        return None, "schema_validation_failure"
    if "tips" in data and data["tips"] is not None and not isinstance(data["tips"], list):
        return None, "schema_validation_failure"
    return data, "ok"


def _merge_content(
    engine_plan: StructuredStudyPlan, llm_plan: StructuredStudyPlan
) -> StructuredStudyPlan:
    """Polish wording only. Engine owns start_time/end_time/kind/title/order."""
    if llm_plan.summary:
        engine_plan.summary = llm_plan.summary.strip()
    if llm_plan.priority_item and engine_plan.priority_item:
        engine_plan.priority_item = PriorityItem(
            title=engine_plan.priority_item.title,
            reason=llm_plan.priority_item.reason or engine_plan.priority_item.reason,
        )
    if llm_plan.tips:
        engine_plan.tips = [t for t in llm_plan.tips if t and t.strip()][:4]

    llm_days = {d.date: d for d in llm_plan.daily_plan}
    for day in engine_plan.daily_plan:
        other = llm_days.get(day.date)
        if not other:
            continue
        for idx, item in enumerate(day.items):
            locked_start = item.start_time
            locked_end = item.end_time
            locked_kind = item.kind
            locked_title = item.title
            if idx >= len(other.items):
                continue
            cand = other.items[idx]
            if (item.kind or "study") == "study":
                if cand.action:
                    item.action = cand.action.strip()
                if cand.reason:
                    item.reason = cand.reason.strip()
            elif cand.action:
                item.action = cand.action.strip()
            item.start_time = locked_start
            item.end_time = locked_end
            item.kind = locked_kind
            item.title = locked_title
    return engine_plan


def detect_language(events: list[ClassifiedCalendarEvent]) -> str:
    hebrew = 0
    latin = 0
    for event in events:
        for chunk in (event.title or "", event.description or ""):
            for ch in chunk:
                if "\u0590" <= ch <= "\u05FF":
                    hebrew += 1
                elif ch.isalpha() and ch.isascii():
                    latin += 1
    return "he" if hebrew > latin else "en"


def build_event_metadata(
    events: list[ClassifiedCalendarEvent], *, today: date
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda e: e.start)[:40]:
        rows.append(
            {
                "id": event.id,
                "title": event.title,
                "category": event.category.value,
                "description": event.description or "",
                "location": event.location or "",
                "start": event.start.isoformat(),
                "end": event.end.isoformat() if event.end else None,
                "priority": _PRIORITY.index(event.category) + 1,
                "days_until": (event.start.date() - today).days,
            }
        )
    return rows


def format_plan_text(plan: StructuredStudyPlan, *, language: str = "en") -> str:
    lines: list[str] = []
    if plan.summary:
        lines.append(plan.summary)
        lines.append("")
    for day in plan.daily_plan:
        try:
            label = date.fromisoformat(day.date).strftime("%A, %d %b")
        except Exception:
            label = day.date
        lines.append(label)
        for item in day.items:
            time_s = ""
            if item.start_time and item.end_time:
                time_s = f"{item.start_time}–{item.end_time} "
            lines.append(f"• {time_s}{item.title}".rstrip())
            if item.action:
                lines.append(f"  {item.action}")
            if item.reason and (item.kind or "study") == "study":
                lines.append(f"  ({item.reason})")
        lines.append("")
    if plan.tips:
        header = "הצעת AI" if language == "he" else "AI suggestion"
        lines.append(f"{header}: {plan.tips[0]}")
        for tip in plan.tips[1:]:
            lines.append(f"• {tip}")
    elif plan.priority_item:
        header = "הצעת AI" if language == "he" else "AI suggestion"
        lines.append(
            f"{header}: {plan.priority_item.title} — {plan.priority_item.reason}"
        )
    return "\n".join(lines).strip()


def _parse_anchor(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_plan_json(raw: str) -> StructuredStudyPlan | None:
    plan, _reason = _parse_plan_json_with_reason(raw)
    return plan


def _parse_plan_json_with_reason(
    raw: str,
) -> tuple[StructuredStudyPlan | None, str]:
    """Return (plan, reason) where reason is ok|empty_response|invalid_json|schema_validation_failure."""
    text = (raw or "").strip()
    if not text:
        return None, "empty_response"
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    data: Any
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None, "invalid_json"
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None, "invalid_json"
    try:
        return StructuredStudyPlan.model_validate(data), "ok"
    except Exception as exc:
        logger.info(
            "stage=ollama_schema_validation_failure detail=%s",
            exc,
        )
        return None, "schema_validation_failure"


def _topics_by_course_key(
    rag_topics: dict[str, list[str]],
    events: list[ClassifiedCalendarEvent],
) -> dict[str, list[str]]:
    """Map normalize_key(course title) → topics for action injection."""
    out: dict[str, list[str]] = {}
    for event in events:
        topics = list(rag_topics.get(str(event.id), []) or [])
        if not topics:
            topics = list(rag_topics.get(course_lookup_key(event.title), []) or [])
        if topics:
            out[normalize_key(event.title)] = topics
    for key, topics in rag_topics.items():
        if key.startswith("course:") and topics:
            out[key.removeprefix("course:")] = list(topics)
    return out


def _match_topics_for_title(
    title: str,
    by_course: dict[str, list[str]],
) -> list[str]:
    key = normalize_key(title)
    if not key:
        return []
    if key in by_course:
        return by_course[key]
    for course_key, topics in by_course.items():
        if course_key and (course_key in key or key in course_key):
            return topics
    return []
