"""
Safety Guardian - Autonomy Framework

Provides safe autonomy for home automation:
- Ask vs Act thresholds
- Fail-safe rules
- Confirmation logic
- Uncertainty handling
- Error/hallucination containment
- Critical system safeguards (HVAC, water valve)
- Audit logging

Philosophy:
- Default to ASK for uncertain situations
- ACT only with high confidence + safety rules satisfied
- Never allow dangerous actions without confirmation
- Always have a fallback/undo path
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import json

from .hil_types import (
    SafetyRule, SafetyDecision, ActionProposal, ActionResult, ActionMode,
    Severity, ScenarioCategory, FusedContext, ConfidenceLevel
)

logger = logging.getLogger(__name__)


# =============================================================================
# SAFETY RULES DATABASE
# =============================================================================

SAFETY_RULES: Dict[str, SafetyRule] = {
    # Water Safety Rules
    "water_valve_close_leak": SafetyRule(
        rule_id="water_valve_close_leak",
        name="Auto-close water valve on leak",
        description="Automatically close main water valve when leak is detected",
        category=ScenarioCategory.WATER_SAFETY,
        severity=Severity.CRITICAL,
        conditions={"leak_detected": True, "confidence": 0.8},
        action_mode=ActionMode.ACT_AND_NOTIFY,
        max_auto_actions=3,
        cooldown_minutes=1,
        requires_confirmation=False,
        fallback_action="notify_user"
    ),
    "water_valve_close_flow": SafetyRule(
        rule_id="water_valve_close_flow",
        name="Auto-close water valve on high flow",
        description="Close valve when abnormal water flow detected",
        category=ScenarioCategory.WATER_SAFETY,
        severity=Severity.HIGH,
        conditions={"flow_anomaly": True, "confidence": 0.85},
        action_mode=ActionMode.ASK,  # Ask first for flow anomalies
        max_auto_actions=1,
        cooldown_minutes=5,
        requires_confirmation=True,
        fallback_action="notify_user"
    ),
    "water_valve_open": SafetyRule(
        rule_id="water_valve_open",
        name="Re-open water valve",
        description="Re-opening water valve requires explicit confirmation",
        category=ScenarioCategory.WATER_SAFETY,
        severity=Severity.MEDIUM,
        conditions={"action": "open_valve"},
        action_mode=ActionMode.ASK,
        max_auto_actions=0,  # Never auto-open
        cooldown_minutes=0,
        requires_confirmation=True,
        fallback_action=None
    ),

    # HVAC Safety Rules
    "hvac_temp_change_small": SafetyRule(
        rule_id="hvac_temp_change_small",
        name="Small temperature adjustment",
        description="Allow small temp changes (±3°F) autonomously",
        category=ScenarioCategory.COMFORT,
        severity=Severity.LOW,
        conditions={"temp_delta_max": 3, "confidence": 0.7},
        action_mode=ActionMode.ACT,
        max_auto_actions=5,
        cooldown_minutes=15,
        requires_confirmation=False,
        fallback_action=None
    ),
    "hvac_temp_change_large": SafetyRule(
        rule_id="hvac_temp_change_large",
        name="Large temperature adjustment",
        description="Large temp changes (>3°F) require confirmation",
        category=ScenarioCategory.COMFORT,
        severity=Severity.MEDIUM,
        conditions={"temp_delta_min": 3},
        action_mode=ActionMode.ASK,
        max_auto_actions=1,
        cooldown_minutes=30,
        requires_confirmation=True,
        fallback_action=None
    ),
    "hvac_extreme_temps": SafetyRule(
        rule_id="hvac_extreme_temps",
        name="Prevent extreme temperatures",
        description="Never set HVAC to extreme temperatures",
        category=ScenarioCategory.COMFORT,
        severity=Severity.HIGH,
        conditions={"temp_min": 55, "temp_max": 85},
        action_mode=ActionMode.ASK,
        max_auto_actions=0,
        cooldown_minutes=0,
        requires_confirmation=True,
        fallback_action="clamp_to_safe_range"
    ),

    # Smoke/CO Rules
    "smoke_alert": SafetyRule(
        rule_id="smoke_alert",
        name="Smoke detection",
        description="Smoke detected - high priority alert",
        category=ScenarioCategory.SECURITY,
        severity=Severity.CRITICAL,
        conditions={"smoke_detected": True},
        action_mode=ActionMode.ACT_AND_NOTIFY,
        max_auto_actions=10,
        cooldown_minutes=0,
        requires_confirmation=False,
        fallback_action="emergency_notify"
    ),
    "co_alert": SafetyRule(
        rule_id="co_alert",
        name="CO detection",
        description="Carbon monoxide detected - critical alert",
        category=ScenarioCategory.SECURITY,
        severity=Severity.CRITICAL,
        conditions={"co_detected": True},
        action_mode=ActionMode.ACT_AND_NOTIFY,
        max_auto_actions=10,
        cooldown_minutes=0,
        requires_confirmation=False,
        fallback_action="emergency_notify"
    ),

    # General Safety
    "unknown_device_action": SafetyRule(
        rule_id="unknown_device_action",
        name="Unknown device action",
        description="Actions on unknown devices require confirmation",
        category=ScenarioCategory.SECURITY,
        severity=Severity.MEDIUM,
        conditions={"device_known": False},
        action_mode=ActionMode.ASK,
        max_auto_actions=0,
        cooldown_minutes=0,
        requires_confirmation=True,
        fallback_action=None
    ),
    "low_confidence_action": SafetyRule(
        rule_id="low_confidence_action",
        name="Low confidence action",
        description="Actions with low confidence require confirmation",
        category=ScenarioCategory.SECURITY,
        severity=Severity.MEDIUM,
        conditions={"confidence_max": 0.6},
        action_mode=ActionMode.ASK,
        max_auto_actions=0,
        cooldown_minutes=0,
        requires_confirmation=True,
        fallback_action=None
    ),
}


class SafetyGuardian:
    """
    Safety guardian that validates all actions before execution.

    Responsibilities:
    1. Validate action proposals against safety rules
    2. Determine ask vs act mode
    3. Apply rate limiting and cooldowns
    4. Log all decisions for audit
    5. Provide fallback actions when primary is blocked
    """

    def __init__(
        self,
        rules: Optional[Dict[str, SafetyRule]] = None,
        db_path: str = "/var/lib/homesight/hsil_memory.db"
    ):
        self.rules = rules or SAFETY_RULES
        self.db_path = db_path

        # Action history for rate limiting
        self.action_history: Dict[str, List[datetime]] = defaultdict(list)

        # Decision audit log (in-memory, persisted periodically)
        self.audit_log: List[Dict[str, Any]] = []

        # Known devices cache
        self.known_devices: set = set()

        # Safe temperature range
        self.safe_temp_min = 55
        self.safe_temp_max = 85

        # Initialize database
        self._init_db()

        logger.info(f"SafetyGuardian initialized with {len(self.rules)} rules")

    def _init_db(self):
        """Initialize audit database"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS safety_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                device_id TEXT,
                decision TEXT NOT NULL,
                action_mode TEXT NOT NULL,
                triggered_rules TEXT,
                reasoning TEXT,
                risk_score REAL,
                context_snapshot TEXT,
                outcome TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_rate_limits (
                rule_id TEXT PRIMARY KEY,
                last_action_time TEXT,
                action_count INTEGER DEFAULT 0,
                reset_time TEXT
            )
        """)

        conn.commit()
        conn.close()

    def register_device(self, device_id: str):
        """Register a known device"""
        self.known_devices.add(device_id)

    async def evaluate(
        self,
        proposal: ActionProposal,
        context: Optional[FusedContext] = None
    ) -> SafetyDecision:
        """
        Evaluate an action proposal and return safety decision.

        Args:
            proposal: Proposed action to evaluate
            context: Current fused context

        Returns:
            SafetyDecision with allowed/blocked status and reasoning
        """
        triggered_rules = []
        risk_factors = []
        modified_action = None
        block_reason = None

        # 1. Check if device is known
        device_known = proposal.target_device_id in self.known_devices
        if not device_known:
            triggered_rules.append("unknown_device_action")
            risk_factors.append(("unknown_device", 0.3))

        # 2. Check confidence level
        if proposal.confidence < 0.6:
            triggered_rules.append("low_confidence_action")
            risk_factors.append(("low_confidence", 0.3))

        # 3. Check action-specific rules
        action_rules = self._get_applicable_rules(proposal, context)
        triggered_rules.extend([r.rule_id for r in action_rules])

        # 4. Check critical safety conditions
        critical_block = self._check_critical_conditions(proposal, context)
        if critical_block:
            block_reason = critical_block

        # 5. Check rate limits
        rate_limited, rate_reason = self._check_rate_limits(proposal, triggered_rules)
        if rate_limited:
            if not block_reason:
                block_reason = rate_reason
            risk_factors.append(("rate_limited", 0.2))

        # 6. Apply temperature clamping for HVAC
        if proposal.action_type == "set_temperature":
            clamped_value, was_clamped = self._clamp_temperature(proposal.value)
            if was_clamped:
                modified_action = {
                    "original_value": proposal.value,
                    "clamped_value": clamped_value,
                    "reason": f"Temperature clamped to safe range ({self.safe_temp_min}-{self.safe_temp_max}°F)"
                }
                proposal.value = clamped_value
                risk_factors.append(("temp_clamped", 0.1))

        # 7. Calculate risk score
        risk_score = self._calculate_risk_score(risk_factors, proposal, context)

        # 8. Determine action mode
        action_mode = self._determine_action_mode(
            proposal, triggered_rules, risk_score, context
        )

        # 9. Build decision
        allowed = block_reason is None
        requires_confirmation = action_mode in [ActionMode.ASK, ActionMode.SUGGEST]

        decision = SafetyDecision(
            allowed=allowed,
            action_mode=action_mode,
            requires_confirmation=requires_confirmation,
            triggered_rules=triggered_rules,
            reasoning=self._build_reasoning(
                proposal, triggered_rules, risk_factors, action_mode
            ),
            risk_score=risk_score,
            block_reason=block_reason,
            modified_action=modified_action,
            timestamp=datetime.now(),
            context_snapshot=self._snapshot_context(context) if context else {}
        )

        # 10. Log decision
        await self._log_decision(proposal, decision)

        return decision

    def _get_applicable_rules(
        self,
        proposal: ActionProposal,
        context: Optional[FusedContext]
    ) -> List[SafetyRule]:
        """Get rules applicable to this proposal"""
        applicable = []

        for rule_id, rule in self.rules.items():
            if self._rule_matches(rule, proposal, context):
                applicable.append(rule)

        return applicable

    def _rule_matches(
        self,
        rule: SafetyRule,
        proposal: ActionProposal,
        context: Optional[FusedContext]
    ) -> bool:
        """Check if a rule matches the proposal/context"""
        conditions = rule.conditions

        # Check action type
        if "action" in conditions:
            if conditions["action"] != proposal.command:
                return False

        # Check confidence
        if "confidence" in conditions:
            if proposal.confidence < conditions["confidence"]:
                return False

        if "confidence_max" in conditions:
            if proposal.confidence > conditions["confidence_max"]:
                return False

        # Check temperature delta
        if "temp_delta_max" in conditions and proposal.action_type == "set_temperature":
            # Would need current temp from context
            pass

        # Check leak detection
        if "leak_detected" in conditions and context:
            if conditions["leak_detected"] and not context.active_leaks:
                return False

        # Check smoke/CO
        if "smoke_detected" in conditions and context:
            if conditions["smoke_detected"] and not context.active_smoke:
                return False

        if "co_detected" in conditions and context:
            if conditions["co_detected"] and not context.active_co:
                return False

        return True

    def _check_critical_conditions(
        self,
        proposal: ActionProposal,
        context: Optional[FusedContext]
    ) -> Optional[str]:
        """Check for critical blocking conditions"""

        # Never allow opening water valve during active leak
        if proposal.command == "open_valve" and context and context.active_leaks:
            return "Cannot open water valve during active leak"

        # Never allow extreme temperatures
        if proposal.action_type == "set_temperature":
            if isinstance(proposal.value, (int, float)):
                if proposal.value < self.safe_temp_min - 5:
                    return f"Temperature {proposal.value}°F is dangerously low"
                if proposal.value > self.safe_temp_max + 5:
                    return f"Temperature {proposal.value}°F is dangerously high"

        return None

    def _check_rate_limits(
        self,
        proposal: ActionProposal,
        triggered_rules: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """Check rate limits for action"""
        now = datetime.now()

        for rule_id in triggered_rules:
            if rule_id not in self.rules:
                continue

            rule = self.rules[rule_id]

            # Clean old history
            cutoff = now - timedelta(hours=1)
            self.action_history[rule_id] = [
                t for t in self.action_history[rule_id] if t > cutoff
            ]

            # Check count
            if len(self.action_history[rule_id]) >= rule.max_auto_actions:
                return True, f"Rate limit exceeded for rule {rule.name}"

            # Check cooldown
            if self.action_history[rule_id]:
                last_action = self.action_history[rule_id][-1]
                cooldown = timedelta(minutes=rule.cooldown_minutes)
                if now - last_action < cooldown:
                    remaining = (last_action + cooldown - now).seconds // 60
                    return True, f"Cooldown active ({remaining} min remaining)"

        return False, None

    def _clamp_temperature(self, value: Any) -> Tuple[Any, bool]:
        """Clamp temperature to safe range"""
        if not isinstance(value, (int, float)):
            return value, False

        if value < self.safe_temp_min:
            return self.safe_temp_min, True
        if value > self.safe_temp_max:
            return self.safe_temp_max, True

        return value, False

    def _calculate_risk_score(
        self,
        risk_factors: List[Tuple[str, float]],
        proposal: ActionProposal,
        context: Optional[FusedContext]
    ) -> float:
        """Calculate overall risk score (0-1)"""
        if not risk_factors:
            return 0.0

        # Base risk from factors
        factor_risk = sum(score for _, score in risk_factors)

        # Adjust for action type
        action_risk_multipliers = {
            "close_valve": 0.3,  # Low risk - safety action
            "open_valve": 1.5,   # High risk - could allow flooding
            "set_temperature": 0.5,
            "turn_on": 0.3,
            "turn_off": 0.3,
            "arm": 0.4,
            "disarm": 0.8,
        }
        multiplier = action_risk_multipliers.get(proposal.command, 1.0)

        # Adjust for urgency
        urgency_factors = {
            Severity.INFO: 0.8,
            Severity.LOW: 0.9,
            Severity.MEDIUM: 1.0,
            Severity.HIGH: 1.1,
            Severity.CRITICAL: 0.7,  # Critical = act fast
        }
        urgency_mult = urgency_factors.get(proposal.urgency, 1.0)

        risk = factor_risk * multiplier * urgency_mult

        return min(1.0, max(0.0, risk))

    def _determine_action_mode(
        self,
        proposal: ActionProposal,
        triggered_rules: List[str],
        risk_score: float,
        context: Optional[FusedContext]
    ) -> ActionMode:
        """Determine whether to ask, suggest, or act"""

        # Critical safety actions can proceed with notify
        if proposal.urgency == Severity.CRITICAL:
            if proposal.command == "close_valve" and context and context.active_leaks:
                return ActionMode.ACT_AND_NOTIFY

        # Check triggered rule modes
        rule_modes = []
        for rule_id in triggered_rules:
            if rule_id in self.rules:
                rule_modes.append(self.rules[rule_id].action_mode)

        # Most restrictive mode wins
        if ActionMode.ASK in rule_modes:
            return ActionMode.ASK
        if ActionMode.SUGGEST in rule_modes:
            return ActionMode.SUGGEST

        # High risk = ask
        if risk_score > 0.6:
            return ActionMode.ASK

        # Medium risk = suggest
        if risk_score > 0.3:
            return ActionMode.SUGGEST

        # Low confidence = ask
        if proposal.confidence < 0.7:
            return ActionMode.ASK

        # High confidence, low risk = act
        if proposal.confidence >= 0.85 and risk_score < 0.2:
            return ActionMode.ACT

        # Default to suggest
        return ActionMode.SUGGEST

    def _build_reasoning(
        self,
        proposal: ActionProposal,
        triggered_rules: List[str],
        risk_factors: List[Tuple[str, float]],
        action_mode: ActionMode
    ) -> str:
        """Build human-readable reasoning"""
        parts = []

        parts.append(f"Evaluating {proposal.command} on {proposal.target_device_id}")
        parts.append(f"Source: {proposal.source}, Confidence: {proposal.confidence:.0%}")

        if triggered_rules:
            parts.append(f"Triggered rules: {', '.join(triggered_rules)}")

        if risk_factors:
            factors_str = ", ".join(f"{name} ({score:.0%})" for name, score in risk_factors)
            parts.append(f"Risk factors: {factors_str}")

        parts.append(f"Decision: {action_mode.value}")

        return " | ".join(parts)

    def _snapshot_context(self, context: FusedContext) -> Dict[str, Any]:
        """Create a minimal snapshot of context for audit"""
        return {
            "timestamp": context.fusion_timestamp.isoformat(),
            "indoor_temp": context.indoor_temp,
            "indoor_humidity": context.indoor_humidity,
            "active_leaks": context.active_leaks,
            "active_smoke": context.active_smoke,
            "active_co": context.active_co,
            "anomaly_count": len(context.anomalies),
            "occupancy": context.behavioral.activity_level if context.behavioral else "unknown"
        }

    async def _log_decision(self, proposal: ActionProposal, decision: SafetyDecision):
        """Log decision for audit"""
        import sqlite3

        log_entry = {
            "timestamp": decision.timestamp.isoformat(),
            "action_type": proposal.action_type,
            "device_id": proposal.target_device_id,
            "decision": "allowed" if decision.allowed else "blocked",
            "action_mode": decision.action_mode.value,
            "triggered_rules": json.dumps(decision.triggered_rules),
            "reasoning": decision.reasoning,
            "risk_score": decision.risk_score,
            "context_snapshot": json.dumps(decision.context_snapshot)
        }

        # Add to in-memory log
        self.audit_log.append(log_entry)
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]

        # Persist to database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO safety_audit
                (timestamp, action_type, device_id, decision, action_mode,
                 triggered_rules, reasoning, risk_score, context_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_entry["timestamp"],
                log_entry["action_type"],
                log_entry["device_id"],
                log_entry["decision"],
                log_entry["action_mode"],
                log_entry["triggered_rules"],
                log_entry["reasoning"],
                log_entry["risk_score"],
                log_entry["context_snapshot"]
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to persist safety audit: {e}")

    def record_action_taken(self, rule_id: str):
        """Record that an action was taken (for rate limiting)"""
        self.action_history[rule_id].append(datetime.now())

    async def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit log entries"""
        return self.audit_log[-limit:]

    async def get_stats(self) -> Dict[str, Any]:
        """Get safety guardian statistics"""
        total_decisions = len(self.audit_log)
        allowed = sum(1 for e in self.audit_log if e["decision"] == "allowed")
        blocked = total_decisions - allowed

        return {
            "total_decisions": total_decisions,
            "allowed": allowed,
            "blocked": blocked,
            "block_rate": blocked / total_decisions if total_decisions > 0 else 0,
            "known_devices": len(self.known_devices),
            "active_rules": len(self.rules)
        }
