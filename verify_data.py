from database import draw_history
from collections import Counter
from datetime import datetime

for gt in ["6/45", "6/55"]:
    docs = list(draw_history.find({"game_type": gt}))
    print(f"--- {gt} ---")
    print(f"Count: {len(docs)}")
    if docs:
        docs.sort(key=lambda x: x['draw_id'])
        day_counts = Counter()
        for d in docs:
            # Parse date DD/MM/YYYY
            dt = datetime.strptime(d['draw_date'], "%d/%m/%Y")
            day_name = dt.strftime("%A") # Monday, Tuesday...
            day_counts[day_name] += 1
            
        print(f"Days of week distribution:")
        for day, count in day_counts.items():
            print(f"  - {day}: {count} draws")
            
        latest = docs[-1]
        print(f"Latest ID: {latest['draw_id']}, Date: {latest['draw_date']}, Numbers: {latest['numbers']}")
