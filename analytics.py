from collections import Counter
import random
from database import get_all_history
from itertools import combinations

def calculate_stats(game_type):
    history = get_all_history(game_type, limit=500)
    if not history:
        return {"hot": [], "cold": [], "all_counts": {}}
    
    all_numbers = []
    for draw in history:
        all_numbers.extend(draw['numbers'])
    
    counts = Counter(all_numbers)
    max_num = 45 if game_type == "6/45" else 55
    
    # Fill in zeros for numbers never drawn
    for i in range(1, max_num + 1):
        if i not in counts:
            counts[i] = 0
            
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    
    hot = [item[0] for item in sorted_items[:10]]
    cold = [item[0] for item in sorted_items[-10:]]
    
    return {
        "hot": hot,
        "cold": cold,
        "all_counts": dict(counts)
    }

def get_ai_lucky_numbers(game_type, combination_mode="mixed"):
    """
    Generate AI lucky numbers.
    combination_mode: 'mixed' (hot + random), 'balanced' (hot + cold + random), 'pure_random'
    """
    stats = calculate_stats(game_type)
    hot = stats['hot']
    cold = stats['cold']
    max_num = 45 if game_type == "6/45" else 55
    all_nums = list(range(1, max_num + 1))
    
    if combination_mode == "mixed":
        # 3 hot + 3 random
        picks = random.sample(hot, min(3, len(hot)))
        remaining = [n for n in all_nums if n not in picks]
        picks.extend(random.sample(remaining, 6 - len(picks)))
    elif combination_mode == "balanced":
        # 2 hot + 2 cold + 2 random
        picks = random.sample(hot, min(2, len(hot)))
        picks.extend(random.sample(cold, min(2, len(cold))))
        remaining = [n for n in all_nums if n not in picks]
        picks.extend(random.sample(remaining, 6 - len(picks)))
    else:
        picks = random.sample(all_nums, 6)
        
    return sorted(picks)

def get_complex_stats(game_type, limit=200):
    history = get_all_history(game_type, limit=limit)
    if not history:
        return {"pairs": [], "triplets": []}
    
    pairs_counts = Counter()
    triplets_counts = Counter()
    
    for draw in history:
        nums = sorted(draw['numbers'])
        # Count pairs
        for pair in combinations(nums, 2):
            pairs_counts[pair] += 1
        # Count triplets
        for triplet in combinations(nums, 3):
            triplets_counts[triplet] += 1
            
    top_pairs = [{"numbers": k, "count": v} for k, v in pairs_counts.most_common(5)]
    top_triplets = [{"numbers": k, "count": v} for k, v in triplets_counts.most_common(5)]
    
    return {
        "pairs": top_pairs,
        "triplets": top_triplets
    }
