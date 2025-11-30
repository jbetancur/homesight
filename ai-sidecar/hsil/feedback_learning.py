"""
User Feedback Learning System

Implements simple online learning from user feedback:
1. User gets a response from the system
2. User provides feedback (thumbs up/down, rating, correction)
3. System stores the interaction in memory
4. System uses this to improve future responses

This is a lightweight reinforcement learning approach that learns
user preferences over time.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from .types import MemoryType

logger = logging.getLogger(__name__)


class FeedbackType(str, Enum):
    """Types of user feedback"""
    POSITIVE = "positive"  # Thumbs up, "good", "thanks"
    NEGATIVE = "negative"  # Thumbs down, "wrong", "no"
    CORRECTION = "correction"  # User provides correct response
    RATING = "rating"  # Numeric rating (1-5)


class UserFeedback:
    """Represents user feedback on a response"""
    def __init__(
        self,
        interaction_id: str,
        feedback_type: FeedbackType,
        rating: Optional[int] = None,
        correction: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ):
        self.interaction_id = interaction_id
        self.feedback_type = feedback_type
        self.rating = rating
        self.correction = correction
        self.timestamp = timestamp or datetime.now()


class FeedbackLearningService:
    """
    Learns from user feedback to improve responses.

    Stores:
    1. User query
    2. System response
    3. User feedback
    4. Context at time of query

    Uses this to:
    - Build preference patterns
    - Identify successful response patterns
    - Avoid unsuccessful patterns
    - Provide examples for few-shot learning
    """

    def __init__(self, db_path: str = "/var/lib/homesight/hsil_memory.db"):
        self.db_path = db_path
        self._init_db()
        logger.info("FeedbackLearningService initialized")

    def _init_db(self):
        """Initialize feedback database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Interaction history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interaction_history (
                id TEXT PRIMARY KEY,
                user_query TEXT NOT NULL,
                system_response TEXT NOT NULL,
                action_taken TEXT,  -- JSON of action if any
                context TEXT,  -- JSON context
                timestamp TIMESTAMP NOT NULL,
                feedback_type TEXT,  -- Set when feedback received
                feedback_rating INTEGER,
                feedback_correction TEXT,
                feedback_timestamp TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_type
            ON interaction_history(feedback_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON interaction_history(timestamp DESC)
        """)

        # Learned preferences
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_key TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                example_count INTEGER DEFAULT 1,
                last_updated TIMESTAMP NOT NULL,
                UNIQUE(preference_key, preference_value)
            )
        """)

        conn.commit()
        conn.close()

        logger.info("Feedback learning database initialized")

    async def record_interaction(
        self,
        interaction_id: str,
        user_query: str,
        system_response: str,
        action_taken: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """Record a user interaction"""
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO interaction_history
            (id, user_query, system_response, action_taken, context, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            interaction_id,
            user_query,
            system_response,
            json.dumps(action_taken) if action_taken else None,
            json.dumps(context) if context else None,
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        logger.debug(f"Recorded interaction: {interaction_id}")

    async def record_feedback(self, feedback: UserFeedback):
        """Record user feedback on an interaction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE interaction_history
            SET feedback_type = ?,
                feedback_rating = ?,
                feedback_correction = ?,
                feedback_timestamp = ?
            WHERE id = ?
        """, (
            feedback.feedback_type.value,
            feedback.rating,
            feedback.correction,
            feedback.timestamp.isoformat(),
            feedback.interaction_id
        ))

        conn.commit()
        conn.close()

        logger.info(
            f"Recorded feedback: {feedback.feedback_type.value} "
            f"for interaction {feedback.interaction_id}"
        )

        # Update learned preferences based on feedback
        await self._update_preferences(feedback)

    async def _update_preferences(self, feedback: UserFeedback):
        """
        Update learned preferences based on feedback.

        This is where the "learning" happens:
        - Positive feedback increases confidence in similar patterns
        - Negative feedback decreases confidence
        - Corrections teach new patterns
        """
        import json

        # Get the interaction
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_query, system_response, action_taken, context
            FROM interaction_history
            WHERE id = ?
        """, (feedback.interaction_id,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        user_query, system_response, action_taken_json, context_json = row

        context = json.loads(context_json) if context_json else {}
        action_taken = json.loads(action_taken_json) if action_taken_json else None

        # Extract learnable patterns
        patterns = await self._extract_patterns(
            user_query,
            system_response,
            action_taken,
            context
        )

        # Update confidence based on feedback
        confidence_delta = 0.0
        if feedback.feedback_type == FeedbackType.POSITIVE:
            confidence_delta = 0.1  # Increase confidence
        elif feedback.feedback_type == FeedbackType.NEGATIVE:
            confidence_delta = -0.1  # Decrease confidence
        elif feedback.feedback_type == FeedbackType.RATING and feedback.rating:
            # Rating 1-5, map to -0.2 to +0.2
            confidence_delta = (feedback.rating - 3) * 0.1

        # Update preferences
        for key, value in patterns.items():
            cursor.execute("""
                INSERT INTO learned_preferences
                (preference_key, preference_value, confidence, example_count, last_updated)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(preference_key, preference_value) DO UPDATE SET
                    confidence = MIN(1.0, MAX(0.0, confidence + ?)),
                    example_count = example_count + 1,
                    last_updated = ?
            """, (
                key,
                value,
                0.5 + confidence_delta,
                datetime.now().isoformat(),
                confidence_delta,
                datetime.now().isoformat()
            ))

        # If correction provided, learn new pattern
        if feedback.correction:
            await self._learn_correction(
                user_query,
                system_response,
                feedback.correction,
                context
            )

        conn.commit()
        conn.close()

        logger.debug(f"Updated preferences based on {feedback.feedback_type.value} feedback")

    async def _extract_patterns(
        self,
        user_query: str,
        system_response: str,
        action_taken: Optional[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Extract learnable patterns from an interaction.

        Returns dict of preference_key -> preference_value
        """
        patterns = {}

        query_lower = user_query.lower()

        # Temperature preferences
        if "cold" in query_lower or "chilly" in query_lower:
            if action_taken and "temperature" in str(action_taken):
                patterns["temperature_when_cold"] = str(action_taken.get("value", "unknown"))

        elif "hot" in query_lower or "warm" in query_lower:
            if action_taken and "temperature" in str(action_taken):
                patterns["temperature_when_hot"] = str(action_taken.get("value", "unknown"))

        # Response style preferences
        if "detail" in query_lower or "explain" in query_lower:
            patterns["preferred_response_style"] = "detailed"
        elif "quick" in query_lower or "brief" in query_lower:
            patterns["preferred_response_style"] = "brief"

        # Action preferences
        if action_taken:
            action_type = action_taken.get("command", "unknown")
            patterns[f"preferred_action_for_{query_lower[:20]}"] = action_type

        return patterns

    async def _learn_correction(
        self,
        user_query: str,
        system_response: str,
        correction: str,
        context: Dict[str, Any]
    ):
        """Learn from user correction"""
        # Store correction as high-confidence preference
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO learned_preferences
            (preference_key, preference_value, confidence, example_count, last_updated)
            VALUES (?, ?, 0.9, 1, ?)
            ON CONFLICT(preference_key, preference_value) DO UPDATE SET
                confidence = 0.9,
                example_count = example_count + 1,
                last_updated = ?
        """, (
            f"correction:{user_query[:50]}",
            correction,
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        logger.info(f"Learned correction for query: {user_query[:50]}")

    async def get_similar_examples(
        self,
        user_query: str,
        limit: int = 3,
        only_positive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get similar successful interactions to use as examples.

        This enables few-shot learning by providing the LLM with
        examples of what worked well in the past.
        """
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Simple keyword matching for now
        # In production, would use semantic similarity via embeddings
        keywords = user_query.lower().split()[:3]
        like_clauses = " OR ".join(["user_query LIKE ?" for _ in keywords])
        like_params = [f"%{kw}%" for kw in keywords]

        sql = f"""
            SELECT user_query, system_response, action_taken, feedback_type, feedback_rating
            FROM interaction_history
            WHERE ({like_clauses})
        """

        if only_positive:
            sql += " AND (feedback_type = 'positive' OR feedback_rating >= 4)"

        sql += " ORDER BY feedback_timestamp DESC LIMIT ?"
        like_params.append(limit)

        cursor.execute(sql, like_params)
        rows = cursor.fetchall()
        conn.close()

        examples = []
        for row in rows:
            examples.append({
                "query": row[0],
                "response": row[1],
                "action": json.loads(row[2]) if row[2] else None,
                "feedback_type": row[3],
                "feedback_rating": row[4]
            })

        return examples

    async def get_learned_preference(self, preference_key: str) -> Optional[str]:
        """Get a learned preference value"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT preference_value, confidence
            FROM learned_preferences
            WHERE preference_key = ?
            ORDER BY confidence DESC, example_count DESC
            LIMIT 1
        """, (preference_key,))

        row = cursor.fetchone()
        conn.close()

        if row and row[1] > 0.5:  # Only return if confidence > 0.5
            return row[0]

        return None

    async def get_all_preferences(self, min_confidence: float = 0.6) -> Dict[str, str]:
        """Get all learned preferences above confidence threshold"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT preference_key, preference_value, confidence
            FROM learned_preferences
            WHERE confidence >= ?
            ORDER BY confidence DESC
        """, (min_confidence,))

        rows = cursor.fetchall()
        conn.close()

        preferences = {}
        for row in rows:
            preferences[row[0]] = row[1]

        return preferences

    async def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total interactions
        cursor.execute("SELECT COUNT(*) FROM interaction_history")
        total_interactions = cursor.fetchone()[0]

        # Feedback counts
        cursor.execute("""
            SELECT feedback_type, COUNT(*)
            FROM interaction_history
            WHERE feedback_type IS NOT NULL
            GROUP BY feedback_type
        """)
        feedback_counts = dict(cursor.fetchall())

        # Learned preferences
        cursor.execute("SELECT COUNT(*) FROM learned_preferences WHERE confidence > 0.6")
        high_confidence_prefs = cursor.fetchone()[0]

        conn.close()

        return {
            "total_interactions": total_interactions,
            "feedback_counts": feedback_counts,
            "high_confidence_preferences": high_confidence_prefs,
            "learning_rate": len(feedback_counts) / max(1, total_interactions)
        }
