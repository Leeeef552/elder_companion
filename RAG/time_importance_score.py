'''
Entry function is `compute_recency_score`


`compute_recency_score`:
- computes the recency score, scoring higher for chunks nearer to the query

- Args:
    - `content_list`: the list of chunks (dicts) retrieved where each should contain either the key for `created_at` or `last_updated`
    - `query`: the user query 
- returns:
    - list of chunks (dicts) with a key (`time_relevance_score`) for the time relevance score
'''

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import re
import math

# Global parameters
TTL_DAYS = 14
HALF_LIFE_DAYS = 6   # you can adjust (e.g., 3 or 7) depending on how steep you want decay


def _get_content_datetime(content: Dict[str, Any]) -> datetime:
    """Extract datetime from content (created_at or last_updated)."""
    if 'created_at' in content:
        return content['created_at']
    elif 'last_updated' in content:
        return content['last_updated']
    else:
        raise ValueError("Content must have either 'created_at' or 'last_updated' key")
    

def _exponential_decay(days_diff: int, half_life_days: int) -> float:
    """Generic exponential decay based on half-life."""
    decay_constant = math.log(2) / half_life_days
    return math.exp(-decay_constant * days_diff)


def _calculate_decay_score(content_time: datetime, reference_time: datetime = None) -> float:
    """Decay scoring with TTL cutoff (fractional days)."""
    if reference_time is None:
        reference_time = datetime.now()

    # --- OLD: integer days ---
    # age_days = (reference_time - content_time).days

    # --- NEW: fractional days (hours + minutes count) ---
    age_days = (reference_time - content_time).total_seconds() / 86400.0

    if age_days > TTL_DAYS:
        return 0.0
    return _exponential_decay(age_days, HALF_LIFE_DAYS)



def compute_recency_score(content_list: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
    """
    Computes and adds a 'recency_score' key directly to each content dict in-place.
    Returns the same list (modified) for chaining.
    """
    for content in content_list:
        try:
            content_time = _get_content_datetime(content)
            score = _calculate_decay_score(content_time)
            content['recency_score'] = round(score, 4)
        except ValueError as e:
            content['recency_score'] = 0.0
            content['error'] = str(e)
    return content_list



# ====================================================
# Sample Date
# ====================================================

sample_data = [
    {
        'id': 'b4e2bf83-6837-47d4-bf39-14cc2407e0de',
        'content': 'User spent $20 on chicken rice yesterday',
        'created_at': datetime(2025, 9, 23, 10, 47, 15),
    },
    {
        'id': 'another-id',
        'content': 'Old content',
        'created_at': datetime(2025, 9, 19, 10, 47, 15),
    },
    {
        'id': 'updated-content',
        'content': 'This was updated recently',
        'created_at': datetime(2025, 8, 1, 10, 47, 15),
        'last_updated': datetime(2025, 9, 25, 14, 30, 0),  # <-- newer than created
    },
    {
        'id': 'ancient-id',
        'content': 'Content from 30 days ago',
        'created_at': datetime(2025, 8, 24, 10, 47, 15),
    },
    {
        'id': 'very-old-id',
        'content': 'Content from 200 days ago',
        'created_at': datetime(2025, 3, 17, 10, 47, 15),
    }
]


now = datetime.now()
print(f"=== CURRENT TIME: {now.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

# ====================================================
# TEST 1: PURE DECAY-BASED SCORING (NO QUERY, NO WINDOW)
# ====================================================
print("=== PURE DECAY-BASED SCORING (IGNORED QUERY, ONLY TIME DECAY) ===")
print("  → All content scored purely by age using exponential decay")
print(f"  → Half-life: {HALF_LIFE_DAYS} days | TTL cutoff: {TTL_DAYS} days\n")

result = compute_recency_score(sample_data, "")  # Query ignored — always decay

for item in result:
    used_field = 'created_at' if 'created_at' in item else 'last_updated'
    content_time = _get_content_datetime(item)
    days_since_content = (now - content_time).days

    # Determine status based on decay curve
    ttl_status = "✅ ACTIVE" if days_since_content <= TTL_DAYS else "❌ EXPIRED"
    half_life_status = "🎯 HALF-LIFE" if abs(days_since_content - HALF_LIFE_DAYS) < 1 else ""
    decay_status = "🟢 NEAR" if days_since_content <= HALF_LIFE_DAYS else "🟡 MID" if days_since_content <= TTL_DAYS/2 else "🔴 FAR"

    print(f"ID: {item['id'][:8]}...")
    print(f"  Content: '{item['content']}'")
    print(f"  Date used: {content_time.strftime('%Y-%m-%d %H:%M')} ({used_field})")
    print(f"  Days since update: {days_since_content} days")
    print(f"  Recency score: {item['recency_score']:.4f} {ttl_status} {half_life_status}")
    print(f"  Decay phase: {decay_status}")
    print()

# ====================================================
# TEST 2: DECAY CURVE REFERENCE (FOR TUNING)
# ====================================================
print("=== DECAY CURVE REFERENCE (for tuning) ===")
print(f"  Half-life: every {HALF_LIFE_DAYS} days, score halves (e.g., 1.0 → 0.5 → 0.25)")
print(f"  TTL cutoff: {TTL_DAYS} days → scores drop to 0 beyond this")
print("-" * 70)

for days in range(0, TTL_DAYS + 1):
    score = _exponential_decay(days, HALF_LIFE_DAYS)
    marker = "🔥" if days == 0 else "🟢" if days <= HALF_LIFE_DAYS else "🟡" if days <= TTL_DAYS/2 else "🔴"
    ttl_indicator = "❌" if days > TTL_DAYS else ""
    print(f"  {days:2d} days since content → score: {score:.4f} {marker} {ttl_indicator}")

print()

# ====================================================
# BONUS: EXPLAIN THE MODEL
# ====================================================
print("=== MODEL BEHAVIOR SUMMARY ===")
print("• Score is calculated ONLY from time since last content update.")
print("• Uses exponential decay: score = 2^(-days / HALF_LIFE_DAYS)")
print("• Scores are clamped to 0 after TTL_DAYS.")


print("=== RAW FUNCTION OUTPUT ===\n")
result = compute_recency_score(sample_data, "I ate yesterday")  # Query ignored — always decay
print(result)