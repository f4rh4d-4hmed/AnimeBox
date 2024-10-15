import requests
import httpx
from bs4 import BeautifulSoup
import json
from tqdm import tqdm
import re
import os
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timedelta
import time
from colorama import Fore, Style, init


"""Remove "#" to get debugging info"""
#import logging
#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
"""Rest"""

init(convert=True)

COOKIE_FILE = 'cookies.txt'
COOKIE_EXPIRATION_HOURS = 48
BASE_URL = "https://anitaku.pe/"
SETTINGS_FILE = 'settings.json'
MAX_RETRIES = 2
RETRY_DELAY = 1

def load_or_create_settings():
    if not os.path.exists(SETTINGS_FILE):
        settings = {
            "email": "",
            "password": "",
            "default": 1
        }
        with open(SETTINGS_FILE, 'w') as file:
            json.dump(settings, file, indent=4)
        print(Fore.YELLOW + f"Created new settings file: {SETTINGS_FILE}")
    else:
        with open(SETTINGS_FILE, 'r') as file:
            settings = json.load(file)
    return settings

def update_settings(email, password):
    settings = load_or_create_settings()
    settings['email'] = email
    settings['password'] = password
    with open(SETTINGS_FILE, 'w') as file:
        json.dump(settings, file, indent=4)
    print(Fore.GREEN + "Settings updated successfully.")

def save_cookies(session):
    cookies = session.cookies.get_dict()
    cookie_data = {
        "cookies": cookies,
        "timestamp": datetime.now().isoformat()
    }
    with open(COOKIE_FILE, 'w') as file:
        json.dump(cookie_data, file, indent=4)

def load_cookies():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, 'r') as file:
            cookie_data = json.load(file)
            return cookie_data
    return None

def cookies_valid(cookie_data):
    saved_time = datetime.fromisoformat(cookie_data['timestamp'])
    if datetime.now() - saved_time < timedelta(hours=COOKIE_EXPIRATION_HOURS):
        return True
    return False

def login_anitaku(email, password):
    login_url = "https://anitaku.pe/login.html"
    headers = {
        "Cache-Control": "max-age=0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Origin": "https://anitaku.pe",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://anitaku.pe/login.html",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en,en-US;q=0.8",
        "Cookie": (
            "gogoanime=p1do1fm9873i77lialag8g8dp4; "
            "_ga=GA1.1.381806101.1725015626; "
            "testcookie=1; "
            "IABGPP_HDR_GppString=DBABLA~BAAAAAAAAgA.QA; "
            "_DABPlus5637_userid_consent_data=6683316680106290; "
            "_sharedID=1cb8f779-1038-4bf7-b9c6-bf6fe0573a45; "
            "cto_bidid=r29B6V83cDV5MkRNRjBlSFhZeUxzdiUyQnNhZ2ZhcERPZGZ1VVNkQk9HMkdTT3ZZMTlYeVd0V2M2ak1FYTBicVpyNmgwclNTN1o1MkFZWWIyTlNGMXRBVGFvQXNLT001ciUyRmR2ZnZINUNFd0NJcnF1OGMlM0Q; "
            "cto_bundle=63qSoV9PaExDRWhaNTlNSlkzYTZqblB0cjJsR2RVRXI2R0UlMkJkWmNLVUp3dkhpS0F5UzZnVWxad0olMkZxdlNoQ2hWbzkzTTJVTEdSNnhQbkFjZzhPUGZuZVVMczZQVzdQbFAyd1BFNTg1U04wbXc5anFPYXJBM0E0Ym50SXdyWGFVMktqRkM5aiUyRkhRWXBCQkhEWnBOb3RDbm5MalElM0QlM0Q; "
            "_ga_X2C65NWLE2=GS1.1.1725015625.1.1.1725015652.0.0.0"
        ),
    }

    session = requests.Session()
    response = session.get(login_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_token = soup.find('input', {'name': '_csrf'})['value']

    login_data = {
        '_csrf': csrf_token,
        'email': email,
        'password': password
    }

    response = session.post(login_url, headers=headers, data=login_data)

    if response.url.endswith("home.html"):
        print(Fore.LIGHTGREEN_EX + "Login successful!")
        save_cookies(session)
        return session
    else:
        print(Fore.LIGHTRED_EX + "Login failed!")
        print(Fore.LIGHTRED_EX + "Response URL:", response.url)
        print(Fore.LIGHTRED_EX + "Response text:", response.text)
        return None

def format_cookies(cookies):
    formatted = []
    for key, value in cookies.items():
        formatted.append({
            "name": key,
            "value": value,
            "domain": "anitaku.so",
            "path": "/"
        })
    return json.dumps(formatted, indent=4)

def search_anime(session, keyword):
    search_url = f'https://anitaku.pe/search.html?keyword={keyword.lower()}'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = session.get(search_url, headers=headers)
    series_list = []
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('ul.items li')
        for i, item in enumerate(items, 1):
            title_tag = item.select_one('p.name a')
            if title_tag:
                title = title_tag.get('title').strip()
                href = title_tag.get('href').strip()
                series_link = BASE_URL + href
                release_tag = item.select_one('p.released')
                release_date = release_tag.text.strip() if release_tag else "Unknown"
                series_list.append((i, title, release_date, series_link))
    return series_list

def display_series(series_list):
    for number, series_title, release_date, _ in series_list:
        print(Fore.LIGHTGREEN_EX + f"{number}. {series_title} - {release_date}")

def get_series_id_and_alias(session, series_link):
    parsed_url = urlparse(series_link)
    series_path = parsed_url.path.strip("/")
    category_url = f"https://anitaku.pe/{series_path}"
    response = session.get(category_url)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        movie_id_input = soup.find('input', {'id': 'movie_id'})
        alias_anime_input = soup.find('input', {'id': 'alias_anime'})
        
        if movie_id_input and alias_anime_input:
            movie_id = movie_id_input.get('value')
            alias_anime = alias_anime_input.get('value')
            return movie_id, alias_anime
        else:
            print(Fore.LIGHTRED_EX + "Error: Could not find required inputs in the HTML.")
            return None, None
    else:
        print(Fore.LIGHTRED_EX + f"Error: Failed to fetch the series page. Status code: {response.status_code}")
        return None, None

def get_episodes_url(session, series_link):
    movie_id, alias_anime = get_series_id_and_alias(session, series_link)
    if movie_id and alias_anime:
        return f"https://ajax.gogocdn.net/ajax/load-list-episode?ep_start=1&ep_end=9999&id={movie_id}&default_ep=0&alias={alias_anime}"
    return None

def get_episodes(session, episodes_url):
    response = session.get(episodes_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    episode_list = []
    episode_elements = soup.select('#episode_related li a')
    
    episode_count = len(episode_elements)
    
    for element in episode_elements:
        episode_number = int(element.find('div', class_='name').text.strip().replace('EP ', ''))
        episode_link = BASE_URL + element['href'].strip()
        episode_list.append((episode_number, episode_link))
    
    episode_list.sort(key=lambda x: x[0])

    return episode_list, episode_count

def get_download_links(session, episode_url):
    if episode_url.startswith('http'):
        url = episode_url
    else:
        url = BASE_URL + episode_url
    
    response = session.get(url)
    download_links = {}

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        download_section = soup.find('div', class_='cf-download')
        if download_section:
            for link in download_section.find_all('a'):
                resolution = link.text.strip()
                download_links[resolution] = link['href']
        else:
            retries = 0
            while retries < MAX_RETRIES:
                retries += 1
                print(Fore.LIGHTYELLOW_EX + f"Retrying to fetch download links for episode {url}. Retry attempt: {retries}/{MAX_RETRIES}")
                time.sleep(RETRY_DELAY)
                response = session.get(url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    download_section = soup.find('div', class_='cf-download')
                    if download_section:
                        for link in download_section.find_all('a'):
                            resolution = link.text.strip()
                            download_links[resolution] = link['href']
                        break
            else:
                print(Fore.LIGHTRED_EX + f"Failed to fetch download links for episode {url} after {MAX_RETRIES} attempts.")
    else:
        print(Fore.LIGHTRED_EX + f"Failed to fetch episode page {url}. Status code: {response.status_code}")

    return download_links

def prompt_download_link(download_links):
    print(Fore.LIGHTBLUE_EX + "Available resolutions:")
    for i, resolution in enumerate(download_links.keys(), 1):
        print(Fore.LIGHTBLUE_EX + f"{i}. {resolution}")

    choice = int(input("Choose a resolution by entering it's number: "))
    if not 1 <= choice <= len(download_links):
        print(Fore.LIGHTRED_EX + "Invalid choice. Exiting.")
        return None

    selected_resolution = list(download_links.keys())[choice - 1]
    return download_links[selected_resolution]

def get_final_download_link(initial_link):
    headers = {
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; Android SDK built for x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.185 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9"
    }
    with httpx.Client(follow_redirects=False) as client:
        retries = 0
        while retries < MAX_RETRIES:
            response = client.get(initial_link, headers=headers)
            if response.status_code in [301, 302]:
                return response.headers['location']
            else:
                retries += 1
                print(Fore.LIGHTRED_EX + f"Could not get the download link of this episode. Retry attempt: {retries}/{MAX_RETRIES}. If it fails try again after current job is compleated.")
                time.sleep(RETRY_DELAY)
    return None

def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def download_file(download_url, episode_link, series_name, replacement_char=' '):
    response = requests.get(download_url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024
    progress_bar = tqdm(total=total_size, unit='iB', unit_scale=True)

    url_path = urlparse(episode_link).path
    episode_match = re.search(r'episode-(\d+)', url_path)
    if episode_match:
        episode_number = episode_match.group(1)
    else:
        episode_number = "999"

    sanitized_series_name = sanitize_filename(series_name.replace(" ", "_").replace("_", replacement_char))
    downloads_dir = Path.home() / "Downloads" / "Anime" / sanitized_series_name
    downloads_dir.mkdir(parents=True, exist_ok=True)

    filename = sanitize_filename(f"{series_name.replace(' ', '_').replace('_', replacement_char)} EP {episode_number}.mp4")
    save_path = downloads_dir / filename

    with open(save_path, 'wb') as file:
        for data in response.iter_content(block_size):
            progress_bar.update(len(data))
            file.write(data)
    progress_bar.close()

    if total_size != 0 and progress_bar.n != total_size:
        print(Fore.LIGHTRED_EX + "Error: Download incomplete")
    else:
        print(Fore.LIGHTGREEN_EX + f"Download complete: {save_path}")

def display_series(series_list):
    series_list.sort(key=lambda x: x[0])
    current_number = 1
    for number, series_title, release_date, _ in series_list:
        while current_number < number:
            print(Fore.LIGHTRED_EX + f"{current_number}. <This was Filtered out as it does not match the keyword.>")
            current_number += 1
        print(Fore.LIGHTGREEN_EX + f"{number}. {series_title} - {release_date}")
        current_number += 1

def check_downloaded_episodes(series_name):
    sanitized_series_name = sanitize_filename(series_name.replace(" ", "_").replace("_", " "))
    downloads_dir = Path.home() / "Downloads" / "Anime" / sanitized_series_name
    if not downloads_dir.exists():
        print(Fore.LIGHTYELLOW_EX + "You don't have any downloaded episodes for this series.")
        return
    downloaded_episodes = []
    for file in downloads_dir.iterdir():
        if file.is_file() and file.suffix == ".mp4":
            match = re.search(r'EP (\d+)', file.stem)
            if match:
                downloaded_episodes.append(int(match.group(1)))
    if downloaded_episodes:
        downloaded_episodes.sort()
        print(Fore.LIGHTYELLOW_EX + f"\nYou already downloaded: {', '.join(map(str, downloaded_episodes))}")
    else:
        print(Fore.LIGHTYELLOW_EX + "\nYou don't have any downloaded episodes for this series.")

def get_user_resolution_choice(available_resolutions):
    print(Fore.LIGHTBLUE_EX + "Available resolutions:")
    for i, resolution in enumerate(available_resolutions, 1):
        print(Fore.LIGHTBLUE_EX + f"{i}. {resolution}")

    while True:
        try:
            choice = int(input(Fore.LIGHTBLUE_EX + "Choose a resolution by entering its number: "))
            if 1 <= choice <= len(available_resolutions):
                return choice - 1  # Return index of the chosen resolution
            else:
                print(Fore.LIGHTRED_EX + "Invalid choice. Please try again.")
        except ValueError:
            print(Fore.LIGHTRED_EX + "Invalid input. Please enter a number.")

def main():
    settings = load_or_create_settings()
    
    if not settings['email'] or not settings['password']:
        print(Fore.YELLOW + "Email and password not found in settings. Please enter them now.\n Create Account in https://anitaku.pe if you don't have an account.\n")
        email = input(Fore.LIGHTGREEN_EX + "Enter your email: ").strip()
        password = input(Fore.LIGHTGREEN_EX + "Enter your password: ").strip()
        update_settings(email, password)
    else:
        email = settings['email']
        password = settings['password']

    cookie_data = load_cookies()

    if cookie_data and cookies_valid(cookie_data):
        session = requests.Session()
        for cookie_name, cookie_value in cookie_data["cookies"].items():
            session.cookies.set(cookie_name, cookie_value)
        print(Fore.YELLOW + "With help of this app you can download most Anime.\n" + 
      Fore.CYAN + "All Anime are collected from GogoAnime.\n" + 
      Fore.RED + "You can find Anime in Downloads folder\n" + 
      Fore.BLUE + "Using saved cookies.")
    else:
        session = login_anitaku(email, password)
    
    choice = None

    if session:
        keyword = input(Fore.LIGHTGREEN_EX + "Which anime would you like to download today? Enter the name:").strip()
        if not keyword:
            print(Fore.LIGHTRED_EX + "Did you forget to enter an anime name? Anyway, I’m exiting now.")
            return
        series_list = search_anime(session, keyword)
        if series_list:
            print(Fore.LIGHTBLUE_EX + "Series found:\n")
            display_series(series_list)
            choice_displayed = int(input(Fore.LIGHTBLUE_EX + "\nSelect a Anime series by typing it's number:"))
            for series_number, series_info, _, series_link in series_list:
                if series_number == choice_displayed:
                    choice = series_info
                    choice_link = series_link
                    break
            if choice is None:
                print(Fore.LIGHTGREEN_EX + "What! I don't know that anime. Well, I am out.")
                return
        else:
            print(Fore.LIGHTRED_EX + "No series found for the Anime name.\nMake sure it's correct. Try Romaji Name.")
            return
    else:
        print(Fore.LIGHTRED_EX + "Login failed. Exiting.")
        return

    if choice is not None:
        series_url = choice_link
        episodes_url = get_episodes_url(session, series_url)
        if episodes_url:
            episode_list, episode_count = get_episodes(session, episodes_url)
            print(Fore.LIGHTGREEN_EX + f"The anime has {episode_count} episodes.")
            check_downloaded_episodes(choice)
            
            while True:
                episode_choice = input(Fore.LIGHTBLUE_EX + "\nNow Let me know what are the episodes You want to download.\nYou can enter them like: 5,3-7, or 1,2,4\n\n:::: ").strip()
                if not episode_choice:
                    print(Fore.LIGHTRED_EX + "You didn't enter any episode numbers. Please try again.")
                    continue
                break

            chosen_episodes = []
            if '-' in episode_choice:
                start, end = map(int, episode_choice.split('-'))
                chosen_episodes = [(number, episode) for number, episode in episode_list if start <= number <= end]
            elif ',' in episode_choice:
                episode_numbers = map(int, episode_choice.split(','))
                for episode_number in episode_numbers:
                    if 1 <= episode_number <= episode_count:
                        chosen_episodes.append((episode_number, next(ep for ep in episode_list if ep[0] == episode_number)[1]))
                    else:
                        print(Fore.LIGHTRED_EX + f"Does that episode exist: {episode_number}")
            else:
                episode_number = int(episode_choice)
                if 1 <= episode_number <= episode_count:
                    chosen_episodes = [(episode_number, next(ep for ep in episode_list if ep[0] == episode_number)[1])]
                else:
                    print(Fore.LIGHTRED_EX + "Invalid episode number. Exiting.")
                    return

            # Get available resolutions from the first episode
            first_episode = chosen_episodes[0][1]
            download_links = get_download_links(session, first_episode)
            if not download_links:
                print(Fore.LIGHTRED_EX + "No download links found. Exiting.")
                return

            available_resolutions = list(download_links.keys())
            selected_resolution_index = get_user_resolution_choice(available_resolutions)
            selected_resolution = available_resolutions[selected_resolution_index]

            for episode_number, episode_link in chosen_episodes:
                download_links = get_download_links(session, episode_link)
                if download_links and selected_resolution in download_links:
                    selected_link = download_links[selected_resolution]
                    final_download_link = get_final_download_link(selected_link)
                    if final_download_link:
                        series_name = choice
                        download_file(final_download_link, episode_link, series_name)
                    else:
                        print(Fore.LIGHTRED_EX + f"Unable to get the final download link for episode {episode_number}.")
                else:
                    print(Fore.LIGHTRED_EX + f"Selected resolution not available for episode {episode_number}. Skipping.")
        else:
            print(Fore.LIGHTRED_EX + "Failed to get the episodes URL. Exiting.")

print(Style.RESET_ALL)

if __name__ == "__main__":
    main()
