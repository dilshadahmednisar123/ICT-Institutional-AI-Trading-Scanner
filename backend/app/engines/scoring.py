"""
ICT Confluence Scoring Engine (100-point heuristic)

Weights (from master prompt, slightly adjusted for current engine coverage):
- HTF directional bias          : 12
- External liquidity context    : 10
- Liquidity sweep quality       : 12
- Displacement quality          : 10
- MSS / structure confirmation  : 12
- FVG quality                   : 8
- Order block / breaker         : 7
- Premium / discount alignment  : 7
- Session timing                : 5   (placeholder until session engine)
- SMT confirmation              : 5   (placeholder)
- PD array confluence           : 5
- Entry quality                 : 4
- Liquidity-based RR            : 3
Total                           : 100

Scores are heuristic confluence scores, NOT calibrated win probabilities.
Mandatory conditions can never be overridden by a high score.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .models.ict_2022 import ICT2022Setup, ModelState
from .fvg import FairValueGap
from .displacement import DisplacementEvent
from .order_blocks import OrderBlock
from .liquidity import LiquiditySweep
from .entry_risk import TradeLevels


@dataclass
class ScoreBreakdown:
    total: float
    components: Dict[str, float]
    classification: str  # Exceptional / High / Moderate / Reject
    notes: List[str]


def score_setup(
    setup: ICT2022Setup,
    has_mss: bool = False,
    session_score: float = 0.0,
    smt_score: float = 0.0,
) -> ScoreBreakdown:
    components: Dict[str, float] = {}
    notes: List[str] = []

    # 1. HTF bias (12)
    if setup.htf_bias == ("bullish" if setup.direction == "BUY" else "bearish"):
        components["htf_bias"] = 12.0
    elif setup.htf_bias == "neutral":
        components["htf_bias"] = 6.0
        notes.append("Neutral HTF bias — half credit")
    else:
        components["htf_bias"] = 0.0
        notes.append("HTF bias counter to trade direction")

    # 2. External liquidity context (10)
    if setup.sweep and setup.sweep.pool.strength >= 60:
        components["liquidity_context"] = 10.0
    elif setup.sweep:
        components["liquidity_context"] = 6.0
    else:
        components["liquidity_context"] = 0.0

    # 3. Sweep quality (12)
    if setup.sweep and setup.sweep.classification in ("confirmed", "with_displacement", "with_mss"):
        components["sweep_quality"] = 12.0
    elif setup.sweep:
        components["sweep_quality"] = 5.0
    else:
        components["sweep_quality"] = 0.0

    # 4. Displacement (10)
    if setup.displacement:
        q = setup.displacement.quality_score
        components["displacement"] = min(10.0, q / 10.0)
    else:
        components["displacement"] = 0.0

    # 5. MSS / structure (12)
    if has_mss:
        components["mss"] = 12.0
    elif setup.state in (ModelState.MSS_CONFIRMED, ModelState.FVG_FORMED, ModelState.ENTRY_ZONE_READY, ModelState.CONFIRMED):
        components["mss"] = 7.0  # partial — we have displacement + structure progress
        notes.append("MSS not explicitly confirmed — partial structure credit")
    else:
        components["mss"] = 0.0

    # 6. FVG quality (8)
    if setup.fvg:
        width_score = min(4.0, setup.fvg.width * 10000)  # rough
        mit = 4.0 if setup.fvg.mitigated_pct < 0.3 else 2.0 if setup.fvg.mitigated_pct < 0.6 else 0.0
        components["fvg"] = min(8.0, width_score + mit)
    else:
        components["fvg"] = 0.0

    # 7. Order block / breaker (7)
    if setup.order_block and not setup.order_block.invalidated:
        components["order_block"] = min(7.0, setup.order_block.quality / 15.0)
    else:
        components["order_block"] = 0.0

    # 8. Premium / Discount (7)
    if setup.direction == "BUY" and setup.premium_discount == "discount":
        components["premium_discount"] = 7.0
    elif setup.direction == "SELL" and setup.premium_discount == "premium":
        components["premium_discount"] = 7.0
    elif setup.premium_discount == "equilibrium":
        components["premium_discount"] = 3.5
    else:
        components["premium_discount"] = 1.0
        notes.append("Trade against preferred premium/discount location")

    # 9. Session (5) — placeholder
    components["session"] = min(5.0, session_score)

    # 10. SMT (5) — placeholder
    components["smt"] = min(5.0, smt_score)

    # 11. PD array confluence (5)
    confluence = 0.0
    if setup.fvg:
        confluence += 2.5
    if setup.order_block:
        confluence += 2.5
    components["pd_confluence"] = confluence

    # 12. Entry quality (4)
    if setup.levels and setup.levels.valid:
        components["entry_quality"] = 4.0
    elif setup.levels:
        components["entry_quality"] = 1.0
    else:
        components["entry_quality"] = 0.0

    # 13. RR (3)
    if setup.levels and setup.levels.risk_reward >= 3.0:
        components["rr"] = 3.0
    elif setup.levels and setup.levels.risk_reward >= 2.0:
        components["rr"] = 2.0
    elif setup.levels and setup.levels.risk_reward >= 1.5:
        components["rr"] = 1.0
    else:
        components["rr"] = 0.0

    total = sum(components.values())
    total = round(min(100.0, total), 1)

    if total >= 90:
        classification = "Exceptional"
    elif total >= 80:
        classification = "High-quality"
    elif total >= 70:
        classification = "Moderate"
    else:
        classification = "Reject / Monitor"

    # Mandatory gate: never promote a high score if core sequence is missing
    if setup.state not in (ModelState.CONFIRMED, ModelState.ENTRY_ZONE_READY, ModelState.FVG_FORMED):
        if total >= 70:
            notes.append("Score reduced — mandatory sequence incomplete")
            total = min(total, 65.0)
            classification = "Reject / Monitor"

    return ScoreBreakdown(
        total=total,
        components=components,
        classification=classification,
        notes=notes,
    )
