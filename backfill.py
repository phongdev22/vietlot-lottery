import requests
from bs4 import BeautifulSoup
from database import save_draw_result
from datetime import datetime
import time

def scrape_history(game_type, stop_date_str="01/01/2026"):
    urls = {
        "6/45": "https://www.minhngoc.net/ket-qua-xo-so/dien-toan-vietlott/mega-6x45.html",
        "6/55": "https://www.minhngoc.net/ket-qua-xo-so/dien-toan-vietlott/power-6x55.html"
    }
    
    url = urls.get(game_type)
    if not url:
        return
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    stop_date = datetime.strptime(stop_date_str, "%d/%m/%Y")
    count = 0
    current_url = url
    should_continue = True
    
    print(f"--- Starting Backfill for {game_type} (Until: {stop_date_str}) ---")

    while should_continue and current_url:
        try:
            print(f"Fetching: {current_url}")
            response = requests.get(current_url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Error {response.status_code}")
                break
                
            soup = BeautifulSoup(response.content, 'html.parser')
            boxes = soup.find_all('div', class_='boxkqxsdientoan')
            
            if not boxes:
                print("No result boxes found on this page.")
                break
                
            for box in boxes:
                try:
                    text_content = box.get_text()
                    
                    # Try to find Date (DD/MM/YYYY)
                    import re
                    date_match = re.search(r'(\d{2}/\d{2}/\d{4})', text_content)
                    if not date_match:
                        continue
                    
                    date_val_str = date_match.group(1)
                    current_box_date = datetime.strptime(date_val_str, "%d/%m/%Y")
                    
                    if current_box_date < stop_date:
                        print(f"Reached stop date {stop_date_str}. Stopping.")
                        should_continue = False
                        break

                    # Try to find Draw ID (#XXXXX)
                    draw_id_match = re.search(r'#(\d+)', text_content)
                    if not draw_id_match:
                        continue
                    draw_id = int(draw_id_match.group(1))
                    
                    # Get Numbers
                    num_tags = box.select('ul.result-number li div.bool')
                    nums = [int(t.text) for t in num_tags]
                    
                    if len(nums) < (7 if game_type == "6/55" else 6):
                        # Some old 6/55 might not display special_num the same way, 
                        # but request said 7 numbers for 6/55
                        if len(nums) < 6: continue
                        
                    main_nums = nums[:6]
                    special_num = nums[6] if game_type == "6/55" and len(nums) >= 7 else None
                    
                    save_draw_result(game_type, draw_id, main_nums, date_val_str, special_number=special_num)
                    count += 1
                except Exception as e:
                    print(f"Error parsing box: {e}")
                    continue
            
            if not should_continue:
                break

            # Find pagination link (the '<' link)
            prev_link = soup.find('a', string='<')
            if prev_link and prev_link.get('href'):
                href = prev_link.get('href')
                current_url = "https://www.minhngoc.net" + href if href.startswith('/') else href
                time.sleep(1)
            else:
                break
                
        except Exception as e:
            print(f"Network error: {e}")
            break
            
    print(f"--- Finished Backfill for {game_type}. Total: {count} ---")

if __name__ == "__main__":
    scrape_history("6/45", stop_date_str="01/01/2026")
    scrape_history("6/55", stop_date_str="01/01/2026")
