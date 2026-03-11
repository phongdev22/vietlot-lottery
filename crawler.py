import requests
from bs4 import BeautifulSoup
from database import save_draw_result
import time
from datetime import datetime
import re

def scrape_vietlott():
    """
    Scrape real data from minhngoc.net
    """
    urls = {
        "6/45": "https://www.minhngoc.net/ket-qua-xo-so/dien-toan-vietlott/mega-6x45.html",
        "6/55": "https://www.minhngoc.net/ket-qua-xo-so/dien-toan-vietlott/power-6x55.html"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    results = []

    for game_type, url in urls.items():
        try:
            print(f"Scraping {game_type} from {url}...")
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Failed to fetch {url}")
                continue
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find Box (The HTML structure provided in user request)
            # The draw ID is inside span#DT6X45_KY_VE (appears to be used for both in the snippet)
            # Find Draw ID - More specific search
            # Try to find the span that actually contains the '#' character
            draw_id_tag = soup.find('span', string=re.compile(r'#\d+'))
            if not draw_id_tag:
                # Fallback to older method but check if it's actually an ID
                draw_id_tag = soup.find('span', id=lambda x: x and ('KY_VE' in x or 'KY' in x))
            
            if not draw_id_tag or '#' not in draw_id_tag.text:
                print(f"Could not find valid draw ID for {game_type}")
                continue
                
            draw_id_text = draw_id_tag.text.replace('#', '').strip()
            draw_id = int(draw_id_text)
            
            # Find numbers
            numbers_tags = soup.select('ul.result-number li div.bool')
            numbers = [int(tag.text) for tag in numbers_tags]
            
            if not numbers:
                print(f"Could not find numbers for {game_type}")
                continue

            # Special number handling for 6/55 (7th ball)
            main_numbers = numbers[:6]
            special_num = None
            if game_type == "6/55" and len(numbers) >= 7:
                special_num = numbers[6] # The 7th ball is special_number
            
            # Find draw date
            header_text = soup.find('h4').text if soup.find('h4') else ""
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', header_text)
            date_str = date_match.group(1) if date_match else datetime.now().strftime("%d/%m/%Y")

            save_draw_result(game_type, draw_id, main_numbers, date_str, special_number=special_num)
            print(f"Saved {game_type} #{draw_id}: {main_numbers} (Bonus: {special_num}) on {date_str}")
            results.append({
                "game_type": game_type, 
                "draw_id": draw_id, 
                "numbers": main_numbers, 
                "special_number": special_num,
                "draw_date": date_str
            })
            
        except Exception as e:
            print(f"Error scraping {game_type}: {e}")
            
    return results

if __name__ == "__main__":
    print("Starting crawler...")
    scrape_vietlott()
    print("Done.")
