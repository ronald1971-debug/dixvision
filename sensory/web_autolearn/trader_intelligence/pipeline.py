"""Trader Intelligence Pipeline — unified end-to-end flow.

Wires existing isolated modules into a single structured pipeline::

    [Source Ingestion]
        ↓
    [Identity + Credibility Filter]
        ↓
    [Content Parsing]
        ↓
    [Strategy Extraction]
        ↓
    [Philosophy Encoding]
        ↓
    [Abstraction Layer]  (pattern encoding + embedding)
        ↓
    [Strategy Synthesis] (recombine atoms from multiple traders)
        ↓
    [Validation / Backtest]  (sandbox gate — pluggable)
        ↓
    [Knowledge Store]  (decay-weighted, outcome-linked)
        ↓
    [Indira Consumption]

Authority quarantine: this module lives in ``sensory/web_autolearn/``
and may NOT import from ``intelligence_engine`` hot-path modules,
``execution_engine``, or ``governance_engine``. It consumes typed
contracts and emits ``TraderPattern`` value objects into the knowledge
store. The evolution engine pulls from the store asynchronously.

All time reads use ``system.time_source`` (INV-15 / B-CLOCK).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from intelligence_engine.trader_modeling.content_parser import (
    ContentParser,
    ContentType,
)
from intelligence_engine.trader_modeling.credibility_filter import (
    CredibilityFilter,
)
from intelligence_engine.trader_modeling.philosophy_encoder import (
    MarketWorldview,
    PhilosophyEncoder,
    TimeHorizon,
)
from intelligence_engine.trader_modeling.strategy_extractor import (
    StrategyExtractor,
)
from learning_engine.attribution.outcome_linker import OutcomeLinker
from learning_engine.trader_abstraction.decay_weighter import DecayWeighter
from learning_engine.trader_abstraction.pattern_encoder import PatternEncoder
from learning_engine.trader_abstraction.strategy_synthesizer import (
    StrategySynthesizer,
)
from learning_engine.vector_memory.trader_embeddings import (
    EmbeddingRecord,
    TraderEmbeddingStore,
)
from sensory.web_autolearn.trader_intelligence.contracts import (
    PipelineResult,
    SourceCategory,
    TraderPattern,
)
from sensory.web_autolearn.trader_intelligence.knowledge_store import (
    TraderKnowledgeStore,
)
from sensory.web_autolearn.trader_intelligence.source_registry import (
    TraderSourceRegistry,
)
from system import time_source

_log = logging.getLogger(__name__)

# Type alias for pluggable validation gate
ValidationGate = Callable[[TraderPattern], bool]


def _default_validation_gate(pattern: TraderPattern) -> bool:
    """Accept patterns with confidence >= 0.3 (placeholder for sandbox)."""
    return pattern.confidence >= 0.3


@dataclass
class _IngestionItem:
    """Internal pipeline state for a single content item."""

    source_id: str
    trader_id: str
    category: SourceCategory
    content: str
    content_type: ContentType = ContentType.TEXT_POST
    worldview: MarketWorldview = MarketWorldview.TREND_FOLLOWING
    horizon: TimeHorizon = TimeHorizon.SWING
    risk_tolerance: float = 0.5
    systematic_score: float = 0.5
    track_record_years: float = 0.0
    verified_returns: bool = False
    meta: dict[str, str] = field(default_factory=dict)


class TraderIntelligencePipeline:
    """Unified pipeline from source ingestion to knowledge store.

    Wires together:
    - CredibilityFilter (identity + credibility)
    - ContentParser (structured extraction)
    - StrategyExtractor (atom extraction)
    - PhilosophyEncoder (philosophy vectors)
    - PatternEncoder (pattern embeddings)
    - TraderEmbeddingStore (vector similarity)
    - StrategySynthesizer (atom recombination)
    - DecayWeighter (temporal relevance)
    - OutcomeLinker (PnL attribution)
    - TraderKnowledgeStore (validated storage)
    - ValidationGate (sandbox / backtest — pluggable)
    """

    def __init__(
        self,
        *,
        source_registry: TraderSourceRegistry | None = None,
        knowledge_store: TraderKnowledgeStore | None = None,
        outcome_linker: OutcomeLinker | None = None,
        embedding_store: TraderEmbeddingStore | None = None,
        validation_gate: ValidationGate | None = None,
        min_credibility: float = 0.3,
        decay_half_life_days: float = 90.0,
        min_synthesis_sources: int = 2,
    ) -> None:
        self._source_registry = source_registry or TraderSourceRegistry()
        self._knowledge_store = knowledge_store or TraderKnowledgeStore(
            decay_half_life_days=decay_half_life_days,
        )
        self._outcome_linker = outcome_linker or OutcomeLinker()
        self._embedding_store = embedding_store or TraderEmbeddingStore(dimension=5)
        self._validation_gate = validation_gate or _default_validation_gate

        # Pipeline stages
        self._credibility_filter = CredibilityFilter(min_score=min_credibility)
        self._content_parser = ContentParser()
        self._strategy_extractor = StrategyExtractor()
        self._philosophy_encoder = PhilosophyEncoder()
        self._pattern_encoder = PatternEncoder()
        self._synthesizer = StrategySynthesizer(min_sources=min_synthesis_sources)
        self._decay_weighter = DecayWeighter(half_life_days=decay_half_life_days)

        self._processed_count = 0

    def ingest(self, items: list[_IngestionItem]) -> PipelineResult:
        """Run the full pipeline on a batch of ingestion items.

        Flow per item:
        1. Credibility filter → reject low-credibility sources
        2. Content parse → structured extraction
        3. Strategy extract → atoms
        4. Philosophy encode → trader vector
        5. Pattern encode → embeddings
        6. Store embeddings for similarity search

        After individual processing:
        7. Synthesize hybrid strategies from atom pool
        8. Validate each pattern through the gate
        9. Store validated patterns in knowledge store
        10. Register patterns with outcome linker
        """
        now_ns = time_source.wall_ns()
        errors: list[str] = []
        credibility_filtered = 0
        all_atoms = []
        all_trader_ids: set[str] = set()
        patterns_extracted = 0
        patterns_accepted = 0
        patterns_rejected = 0
        validation_failures = 0

        # --- Per-item stages (1-6) ---
        for item in items:
            try:
                # Stage 1: Credibility filter
                assessment = self._credibility_filter.assess(
                    trader_id=item.trader_id,
                    track_record_years=item.track_record_years,
                    verified_returns=item.verified_returns,
                )
                if not assessment.pass_filter:
                    credibility_filtered += 1
                    continue

                # Stage 2: Content parse
                parsed = self._content_parser.parse(
                    content_id=f"{item.source_id}_{item.trader_id}_{now_ns}",
                    content_type=item.content_type,
                    trader_id=item.trader_id,
                    raw_text=item.content,
                    ts_ns=now_ns,
                )

                # Stage 3: Strategy extraction (uses parsed content)
                atoms = self._strategy_extractor.extract_from_observation(
                    trader_id=item.trader_id,
                    philosophy=item.worldview.value,
                    content=parsed.raw_text,
                    ts_ns=now_ns,
                )
                all_atoms.extend(atoms)
                all_trader_ids.add(item.trader_id)

                # Stage 4: Philosophy encoding
                philosophy = self._philosophy_encoder.encode(
                    trader_id=item.trader_id,
                    worldview=item.worldview,
                    horizon=item.horizon,
                    risk_tolerance=item.risk_tolerance,
                    diversification_pref=0.5,
                    systematic_score=item.systematic_score,
                    domains={"crypto": 1.0},
                )

                # Stage 5: Pattern encoding (per atom)
                for atom in atoms:
                    self._pattern_encoder.encode(
                        pattern_id=atom.atom_id,
                        trader_id=item.trader_id,
                        pattern_type=atom.category.value,
                        success_rate=atom.confidence,
                        frequency=1,
                        applicable_regimes=list(atom.applicable_regimes),
                        conditions=atom.parameters,
                        ts_ns=now_ns,
                    )

                # Stage 6: Store philosophy embedding
                self._embedding_store.add(
                    EmbeddingRecord(
                        record_id=item.trader_id,
                        vector=philosophy.embedding,
                        metadata={
                            "worldview": philosophy.worldview.value,
                            "horizon": philosophy.horizon.value,
                            "source": item.source_id,
                            "category": item.category.value,
                        },
                    )
                )

            except Exception as exc:
                errors.append(f"{item.trader_id}: {exc}")
                _log.warning("pipeline error for %s: %s", item.trader_id, exc)

        # --- Cross-item stages (7-10) ---

        # Stage 7: Synthesize hybrid strategies from atom pool
        synthesized = self._synthesizer.synthesize(all_atoms, ts_ns=now_ns)

        # Convert synthesized strategies + raw atoms into TraderPattern objects
        candidate_patterns: list[TraderPattern] = []

        # From synthesized strategies
        for strat in synthesized:
            entry_desc = strat.entry_atom.description if strat.entry_atom else ""
            exit_desc = strat.exit_atom.description if strat.exit_atom else ""
            risk_desc = strat.risk_atom.description if strat.risk_atom else ""
            pattern = TraderPattern(
                pattern_id=strat.strategy_id,
                source_trader_id="|".join(strat.source_traders),
                source_category=SourceCategory.ALGORITHMIC,
                strategy_type="SYNTHESIZED",
                entry_logic=entry_desc,
                exit_logic=exit_desc,
                risk_model=risk_desc,
                context_conditions=strat.applicable_regimes,
                confidence=strat.composite_confidence,
                credibility_score=strat.composite_confidence,
                ts_ns=now_ns,
            )
            candidate_patterns.append(pattern)
            patterns_extracted += 1

        # From individual high-confidence atoms (non-synthesized)
        for atom in all_atoms:
            pattern = TraderPattern(
                pattern_id=atom.atom_id,
                source_trader_id=atom.source_trader,
                source_category=SourceCategory.DISCRETIONARY,
                strategy_type=atom.category.value,
                entry_logic=atom.description if atom.category.value == "ENTRY" else "",
                exit_logic=atom.description if atom.category.value == "EXIT" else "",
                risk_model=atom.description if atom.category.value == "RISK" else "",
                context_conditions=atom.applicable_regimes,
                confidence=atom.confidence,
                credibility_score=atom.confidence,
                ts_ns=now_ns,
            )
            candidate_patterns.append(pattern)
            patterns_extracted += 1

        # Stage 8: Validation gate
        for pattern in candidate_patterns:
            try:
                if self._validation_gate(pattern):
                    # Stage 9: Store in knowledge store
                    self._knowledge_store.ingest(pattern)
                    # Stage 10: Register with outcome linker
                    self._outcome_linker.register_pattern_source(
                        pattern.pattern_id,
                        pattern.source_trader_id,
                    )
                    patterns_accepted += 1
                else:
                    patterns_rejected += 1
            except Exception as exc:
                validation_failures += 1
                errors.append(f"validation: {pattern.pattern_id}: {exc}")

        elapsed_ns = time_source.wall_ns() - now_ns
        self._processed_count += len(items)

        return PipelineResult(
            patterns_extracted=patterns_extracted,
            patterns_accepted=patterns_accepted,
            patterns_rejected=patterns_rejected,
            sources_processed=len(items),
            credibility_filtered=credibility_filtered,
            validation_failures=validation_failures,
            elapsed_ns=elapsed_ns,
            errors=tuple(errors),
        )

    @property
    def knowledge_store(self) -> TraderKnowledgeStore:
        return self._knowledge_store

    @property
    def outcome_linker(self) -> OutcomeLinker:
        return self._outcome_linker

    @property
    def embedding_store(self) -> TraderEmbeddingStore:
        return self._embedding_store

    @property
    def source_registry(self) -> TraderSourceRegistry:
        return self._source_registry

    @property
    def processed_count(self) -> int:
        return self._processed_count
