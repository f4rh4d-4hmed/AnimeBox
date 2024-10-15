import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
from bs4 import BeautifulSoup
import json
import time
from tqdm import tqdm
from urllib.parse import urlparse
from pathlib import Path
import re
import os
from datetime import datetime, timedelta
import threading
import sv_ttk
import concurrent.futures

"""Remove "#" to get debugging info"""
# import logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

COOKIE_FILE = 'cookies.txt'
COOKIE_EXPIRATION_HOURS = 72
BASE_URL = "https://anitaku.pe/"
MAX_RETRIES = 2
RETRY_DELAY = 1
SETTINGS_FILE = 'settings.json'

def save_settings(email, password):
    settings_data = {
        "email": email,
        "password": password
    }
    with open(SETTINGS_FILE, 'w') as file:
        json.dump(settings_data, file, indent=4)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as file:
            return json.load(file)
    return None


class AnimeDownloaderApp:
    def __init__(self, root, email, password):

        self.root = root
        self.root.title("Anime Downloader")
        self.root.geometry("800x660")
        sv_ttk.set_theme("dark")

        settings = load_settings()
        if settings:
            email = settings["email"]
            password = settings["password"]
        else:
            email, password = self.prompt_for_credentials()

        self.session = self.init_session(email, password)
        self.preferred_resolution = None

        self.search_frame = ttk.Frame(root)
        self.search_frame.pack(pady=10, fill='x')

        self.last_episode_message = ""

        self.search_label = ttk.Label(self.search_frame, text="  Search Anime: ")
        self.search_label.pack(side='left')

        self.search_entry = ttk.Entry(self.search_frame, width=72)
        self.search_entry.pack(side='left', padx=(0, 10))

        self.search_button = ttk.Button(self.search_frame, text="Search", command=self.search_anime)
        self.search_button.pack(side='left', padx=(10, 0))
        self.root.bind('<Return>', self.on_enter)

        self.tree = ttk.Treeview(root, columns=("Title", "Release Date"), show="headings")

        self.tree.heading("Title", text="Title")
        self.tree.heading("Release Date", text="Release Date")
        self.tree.pack(pady=20, fill="both", expand=True)
        self.tree.bind("<Double-1>", self.on_series_selected)

        self.episode_frame = ttk.Frame(root)
        self.episode_frame.pack(pady=10)

        self.start_label = ttk.Label(self.episode_frame, text="Start Episode:")
        self.start_label.pack(side="left")

        self.start_entry = ttk.Entry(self.episode_frame, width=5)
        self.start_entry.pack(side="left", padx=5)

        self.end_label = ttk.Label(self.episode_frame, text="End Episode:")
        self.end_label.pack(side="left")

        self.end_entry = ttk.Entry(self.episode_frame, width=5)
        self.end_entry.pack(side="left", padx=5)

        self.download_button = ttk.Button(root, text="Download", command=self.start_download)
        self.download_button.pack(pady=20)

        self.progress_label = ttk.Label(root, text="")
        self.progress_label.pack(pady=10)

        self.progress_bar = ttk.Progressbar(root, length=500, mode='determinate')
        self.progress_bar.pack(pady=10)
        self.selected_series = None
        self.episodes = []

        self.comment_box = scrolledtext.ScrolledText(root, height=5, width=70, wrap=tk.WORD)
        self.comment_box.pack(pady=10, padx=10, fill=tk.X, expand=True)
        self.comment_box.config(state=tk.DISABLED)
        
        self.comment_box.tag_configure("red", foreground="#FF9999", font=("TkDefaultFont", 10, "bold"))
        self.comment_box.tag_configure("green", foreground="#99FF99", font=("TkDefaultFont", 10, "bold"))
        self.comment_box.tag_configure("blue", foreground="#99CCFF", font=("TkDefaultFont", 10, "bold"))
        self.comment_box.tag_configure("yellow", foreground="#FFFF99", font=("TkDefaultFont", 10, "bold"))

        self.selected_series = None
        self.episodes = []

        self.loading_label = ttk.Label(root, text="")
        self.loading_label.pack(pady=5)

    def on_enter(self, event):
        if self.root.focus_get() == self.root:
            self.update_search_results()

    def prompt_for_credentials(self):
        login_window = tk.Toplevel(self.root)
        login_window.title("Login")

        login_window.transient(self.root)
        login_window.grab_set()
        login_window.focus_force()

        ttk.Label(login_window, text="Email:").pack(pady=5)
        email_entry = ttk.Entry(login_window, width=30)
        email_entry.pack(pady=5)

        ttk.Label(login_window, text="Password:").pack(pady=5)
        password_entry = ttk.Entry(login_window, width=30, show="*")
        password_entry.pack(pady=5)

        credentials = {"email": "", "password": ""}

        def on_ok():
            credentials["email"] = email_entry.get()
            credentials["password"] = password_entry.get()
            save_settings(credentials["email"], credentials["password"])
            login_window.destroy()

            self.restart_app(credentials["email"], credentials["password"])

        ttk.Button(login_window, text="Login", command=on_ok).pack(pady=10)

        self.root.wait_window(login_window)

    def restart_app(self, email, password):
        self.root.destroy()
        new_root = tk.Tk()
        app = AnimeDownloaderApp(new_root, email, password)
        new_root.mainloop()

    def save_settings(email, password):
        settings = {
            "email": email,
            "password": password
        }
        with open('settings.json', 'w') as file:
            json.dump(settings, file, indent=4)

    def init_session(self, email, password):
        cookie_data = self.load_cookies()
        if cookie_data and self.cookies_valid(cookie_data):
            session = requests.Session()
            cookies = cookie_data["cookies"]
            session.cookies.update(cookies)
        else:
            session = self.login_anitaku(email, password)
            self.save_cookies(session)
        return session

    def save_cookies(self, session):
        cookies = session.cookies.get_dict()
        cookie_data = {
            "cookies": cookies,
            "timestamp": datetime.now().isoformat()
        }
        with open(COOKIE_FILE, 'w') as file:
            json.dump(cookie_data, file, indent=4)

    def load_cookies(self):
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, 'r') as file:
                cookie_data = json.load(file)
                return cookie_data
        return None

    def cookies_valid(self, cookie_data):
        saved_time = datetime.fromisoformat(cookie_data['timestamp'])
        if datetime.now() - saved_time < timedelta(hours=COOKIE_EXPIRATION_HOURS):
            return True
        return False

    def login_anitaku(self, email, password):
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
            return session
        else:
            return None

    def search_anime(self):
        keyword = self.search_entry.get().strip()
        if not keyword:
            messagebox.showerror("Error", "Please enter a keyword to search.")
            return
        
        self.loading_label.config(text="Searching...")
        self.root.update()
        threading.Thread(target=self.threaded_search, args=(keyword,), daemon=True).start()

    def threaded_search(self, keyword):
        series_list = self.perform_search(keyword)
        
        self.root.after(0, self.update_search_results, series_list, keyword)

    def update_search_results(self, series_list, keyword):
        self.populate_tree(series_list)
        self.update_comment(f"If you see any error you may need to update the app or create new issue in Github\nYou have searched for '{keyword}'", "blue")
        self.loading_label.config(text="")

    def perform_search(self, keyword):
        search_url = f'https://anitaku.pe/search.html?keyword={keyword.lower()}'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = self.session.get(search_url, headers=headers)
        series_list = []
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('ul.items li')
            for i, item in enumerate(items, 1):
                title_tag = item.select_one('p.name a')
                if title_tag:
                    title = title_tag.get('title').strip()
                    href = title_tag.get('href').strip()
                    series_link = "https://anitaku.pe" + href
                    release_tag = item.select_one('p.released')
                    release_date = release_tag.text.strip() if release_tag else "Unknown"
                    series_list.append((i, title, release_date, series_link))
        return series_list

    def populate_tree(self, series_list):
        self.tree.delete(*self.tree.get_children())
        for number, title, release_date, series_link in series_list:
            self.tree.insert("", "end", values=(title, release_date, series_link))

    def on_series_selected(self, event):
        item = self.tree.selection()[0]
        self.selected_series = self.tree.item(item, "values")[0]
        series_link = self.tree.item(item, "values")[2]
        
        self.loading_label.config(text="Loading episodes...")
        self.root.update()
        threading.Thread(target=self.threaded_get_episodes, args=(series_link,), daemon=True).start()

    def threaded_get_episodes(self, series_link):
        self.episodes = self.get_episodes(series_link)
        
        self.root.after(0, self.update_episodes_info)

    def update_episodes_info(self):
        self.update_comment(f"You have selected '{self.selected_series}'.", "yellow")
        self.loading_label.config(text="")
        self.update_comment(f"The anime has {len(self.episodes)} episodes.", "red")
        self.loading_label.config(text="")
        
        threading.Thread(target=self.check_downloaded_episodes, daemon=True).start()

    def update_comment(self, message, color=None):
        if message.startswith("Downloaded episodes for") and message == self.last_episode_message:
            return

        self.comment_box.config(state=tk.NORMAL)
        if color and color in ["red", "green", "blue", "yellow"]:
            self.comment_box.insert(tk.END, message + "\n", color)
        else:
            self.comment_box.insert(tk.END, message + "\n")
        self.comment_box.see(tk.END)
        self.comment_box.config(state=tk.DISABLED)
        if message.startswith("Downloaded episodes for"):
            self.last_episode_message = message

    def get_series_id_and_alias(self, series_link):
        parsed_url = urlparse(series_link)
        series_path = parsed_url.path.strip("/")
        category_url = f"https://anitaku.pe/{series_path}"
        response = self.session.get(category_url)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            movie_id_input = soup.find('input', {'id': 'movie_id'})
            alias_anime_input = soup.find('input', {'id': 'alias_anime'})

            if movie_id_input and alias_anime_input:
                movie_id = movie_id_input.get('value')
                alias_anime = alias_anime_input.get('value')
                return movie_id, alias_anime
            else:
                return None, None
        else:
            return None, None

    def get_episodes_url(self, series_link):
        movie_id, alias_anime = self.get_series_id_and_alias(series_link)
        if movie_id and alias_anime:
            return f"https://ajax.gogocdn.net/ajax/load-list-episode?ep_start=1&ep_end=9999&id={movie_id}&default_ep=0&alias={alias_anime}"
        return None

    def get_episodes(self, series_link):
        episodes_url = self.get_episodes_url(series_link)
        if episodes_url:
            response = self.session.get(episodes_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            episode_elements = soup.select('#episode_related li a')

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self.process_episode, element) for element in episode_elements]
                episode_list = [future.result() for future in concurrent.futures.as_completed(futures)]

            episode_list.sort(key=lambda x: x[0])
            return episode_list
        else:
            return []

    def process_episode(self, element):
        episode_number = int(element.find('div', class_='name').text.strip().replace('EP ', ''))
        episode_link = BASE_URL + element['href'].strip()
        return (episode_number, episode_link)

    def get_download_links(self, episode_url):
        if episode_url.startswith('http'):
            url = episode_url
        else:
            url = BASE_URL + episode_url


        response = self.session.get(url)
        download_links = {}

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            download_section = soup.find('div', class_='cf-download')
            if download_section:
                for link in download_section.find_all('a'):
                    resolution = link.text.strip()
                    download_links[resolution] = link['href']
            else:
                for _ in range(MAX_RETRIES):
                    response = self.session.get(url)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        download_section = soup.find('div', class_='cf-download')
                        if download_section:
                            for link in download_section.find_all('a'):
                                resolution = link.text.strip()
                                download_links[resolution] = link['href']
                            break
                    time.sleep(RETRY_DELAY)
                else:
                    self.progress_label.config(text=f"Failed to fetch download links for episode {url} after {MAX_RETRIES} attempts.")
        else:
            self.progress_label.config(text=f"Failed to fetch episode page {url}. Status code: {response.status_code}")
        
        return download_links

    def prompt_download_link(self, download_links):
        if self.preferred_resolution and self.preferred_resolution in download_links:
            return download_links[self.preferred_resolution]

        resolutions = list(download_links.keys())
        if not resolutions:
            messagebox.showinfo("No Links", "No download links found.")
            return None
    
        choice_window = tk.Toplevel(self.root)
        choice_window.title("Choose Resolution")
        choice_window.geometry("300x230")

        ttk.Label(choice_window, text="Available resolutions:").pack(pady=10)
        resolution_var = tk.StringVar(value=resolutions[0])

        for resolution in resolutions:
            ttk.Radiobutton(choice_window, text=resolution, variable=resolution_var, value=resolution).pack(anchor="w")
    
        remember_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(choice_window, text="Remember my choice", variable=remember_var).pack(pady=5)

        selected_resolution = tk.StringVar(value="")

        def on_ok():
            selected_resolution.set(resolution_var.get())
            if remember_var.get():
                self.preferred_resolution = selected_resolution.get()
            choice_window.destroy()

        ttk.Button(choice_window, text="OK", command=on_ok).pack(pady=10)

        self.root.wait_window(choice_window)

        return download_links.get(selected_resolution.get())

    def process_resolution_choice(self, selected_resolution, download_links, choice_window):
        if selected_resolution in download_links:
            choice_window.destroy()
            self.download_file(download_links[selected_resolution], "", self.selected_series)
        else:
            messagebox.showerror("Error", "Invalid choice. Exiting.")

    def get_final_download_link(self, initial_link):
        headers = {
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; Android SDK built for x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.185 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9"
        }
        retries = 0
        while retries < MAX_RETRIES:
            response = self.session.get(initial_link, headers=headers)
            if response.status_code in [301, 302]:
                return response.headers['location']
            else:
                retries += 1
                self.progress_label.config(text=f"Retry attempt {retries}/{MAX_RETRIES}.")
                self.root.update()
                time.sleep(RETRY_DELAY)
        return None

    def sanitize_filename(self, filename):
        return re.sub(r'[<>:"/\\|?*]', '', filename)

    def download_file(self, download_url, episode_number, series_name, replacement_char=' '):
        response = requests.get(download_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        downloaded_size = 0
        start_time = time.time()

        sanitized_series_name = self.sanitize_filename(series_name.replace(" ", "_").replace("_", replacement_char))
        downloads_dir = Path.home() / "Downloads" / "Anime" / sanitized_series_name
        downloads_dir.mkdir(parents=True, exist_ok=True)

        filename = self.sanitize_filename(f"{sanitized_series_name} EP {episode_number}.mp4")
        save_path = downloads_dir / filename

        with open(save_path, 'wb') as file:
            for data in response.iter_content(block_size):
                downloaded_size += len(data)
                file.write(data)
                elapsed_time = time.time() - start_time
                speed_kbps = (downloaded_size / 1024) / elapsed_time if elapsed_time > 0 else 0
                
                self.root.after(0, self.update_progress_bar, downloaded_size, total_size, speed_kbps)

        if total_size != 0 and downloaded_size != total_size:
            self.progress_label.config(text="Error: Download incomplete")
        else:
            self.update_comment(f"Download complete: {save_path}", "red")

    def update_progress_bar(self, downloaded_size, total_size, speed_kbps):
        progress_percent = (downloaded_size / total_size) * 100
        self.progress_bar['value'] = progress_percent

        downloaded_mb = downloaded_size / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        
        self.progress_label.config(
            text=f"{downloaded_mb:.1f}/{total_mb:.1f} MB ~ {speed_kbps:.1f} KB/s"
        )

    def start_download(self):
        start_ep = self.start_entry.get().strip()
        end_ep = self.end_entry.get().strip()
        if not start_ep.isdigit() or not end_ep.isdigit():
            messagebox.showerror("Error", "Please enter valid episode numbers.")
            return

        start_ep = int(start_ep)
        end_ep = int(end_ep)
        if start_ep > end_ep or start_ep < 1 or end_ep > len(self.episodes):
            messagebox.showerror("Error", "Invalid episode range or select an Anime")
            return

        self.update_comment(f"Starting download of episodes {start_ep} to {end_ep}", "blue")
        threading.Thread(target=self.download_episodes, args=(start_ep, end_ep)).start()

    def download_episodes(self, start_ep, end_ep):
        for ep_num, episode_link in self.episodes:
            if start_ep <= ep_num <= end_ep:
                self.progress_label.config(text=f"Downloading episode {ep_num}...")
                self.update_comment(f"Downloading episode {ep_num}...", "yellow")
                self.progress_bar['value'] = 0
            
                download_links = self.get_download_links(episode_link)
                if not download_links:
                    self.progress_label.config(text=f"No download links found for episode {ep_num}.")
                    self.update_comment(f"No download links found for episode {ep_num}.", "red")
                    continue
            
                download_url = self.prompt_download_link(download_links)
                if not download_url:
                    self.progress_label.config(text=f"No resolution chosen for episode {ep_num}.")
                    self.update_comment(f"No resolution chosen for episode {ep_num}.", "red")
                    continue

                self.download_file(download_url, ep_num, self.selected_series)
                self.update_comment(f"Episode {ep_num} downloaded successfully.", "green")
                messagebox.showinfo("Download Complete", f"Episode {ep_num} downloaded successfully.", "red")
                self.progress_bar['value'] = 0

    def download_episodes(self, start_ep, end_ep):
        for ep_num, episode_link in self.episodes:
            if start_ep <= ep_num <= end_ep:
                self.progress_label.config(text=f"Downloading episode {ep_num}...")
                self.progress_bar['value'] = 0
            
                download_links = self.get_download_links(episode_link)
                if not download_links:
                    self.progress_label.config(text=f"No download links found for episode {ep_num}.")
                    continue
            
                download_url = self.prompt_download_link(download_links)
                if not download_url:
                    self.progress_label.config(text=f"No resolution chosen for episode {ep_num}.")
                    continue

                self.download_file(download_url, ep_num, self.selected_series)
                self.update_comment("Download Complete. " + f"Episode {ep_num} downloaded successfully.", "blue")
                self.progress_bar['value'] = 0

    def check_downloaded_episodes(self):
        if not self.selected_series:
            self.update_comment("No series selected.", "blue")
            return

        sanitized_series_name = self.sanitize_filename(self.selected_series.replace(" ", "_").replace("_", " "))
        downloads_dir = Path.home() / "Downloads" / "Anime" / sanitized_series_name

        if not downloads_dir.exists():
            self.update_comment(f"No downloaded episodes found for {self.selected_series}.", "yellow")
            return

        downloaded_episodes = []
        for file in os.listdir(downloads_dir):
            if file.endswith(".mp4"):
                match = re.search(r'EP (\d+)', file)
                if match:
                    downloaded_episodes.append(int(match.group(1)))

        if downloaded_episodes:
            downloaded_episodes.sort()
            message = f"Downloaded episodes for {self.selected_series}: {', '.join(map(str, downloaded_episodes))}"
        else:
            message = f"No downloaded episodes found for {self.selected_series}."

        self.update_comment(message, "green")

def main():
    root = tk.Tk()
    email = None
    password = None
    session = requests.Session()

    app = AnimeDownloaderApp(root, email, password)
    root.mainloop()

if __name__ == "__main__":
    main()
