# Import necessary libraries
import os
import time
import random
import pandas as pd
import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
load_dotenv()   # reads .env into os.environ

# ----------------------------
# Configuration
# ----------------------------
MAX_SCROLLS = 8     # max full-page scrolls per run
MAX_POSTS   = 25    # max posts to process per run
SCROLL_PAUSE = 1.5  # base scroll pause (seconds)
HUMAN_HOUR_START = 9
HUMAN_HOUR_END   = 18

# ----------------------------
# Human-hours guard (optional)
# ----------------------------
current_hour = datetime.now().hour
if current_hour < HUMAN_HOUR_START or current_hour >= HUMAN_HOUR_END:
    print("Outside of human browsing hours. Exiting.")
    exit()

# ----------------------------
# Credentials from .env
# ----------------------------
username = os.getenv("LINKEDIN_USER")
password = os.getenv("LINKEDIN_PASS")
if not username or not password:
    raise RuntimeError("Please set LINKEDIN_USER and LINKEDIN_PASS in your environment.")

# ----------------------------
# Launch stealth Chrome
# ----------------------------
options = uc.ChromeOptions()
options.add_argument("--start-maximized")
# options.add_argument("--user-data-dir=/path/to/your/chrome/profile")  # if desired

browser = uc.Chrome(
    driver_executable_path=ChromeDriverManager().install(),
    options=options
)

# ----------------------------
# Log in to LinkedIn
# ----------------------------
browser.get("https://www.linkedin.com/login")
time.sleep(random.uniform(1, 3))

browser.find_element(By.ID, "username").send_keys(username)
time.sleep(random.uniform(0.5, 1.5))
browser.find_element(By.ID, "password").send_keys(password)
time.sleep(random.uniform(0.5, 1.5))
browser.find_element(By.ID, "password").submit()
time.sleep(random.uniform(3, 5))

# ----------------------------
# Navigate and scroll
# ----------------------------
page = "https://www.linkedin.com/in/ariel-wertlen-spilkin-73958374/"
try:
    # give the page up to 30s to load before timing out
    browser.set_page_load_timeout(30)
    browser.get(f"{page}/posts")
except TimeoutException:
    print("Warning: page load timed out, continuing with what we have…")

# wait up to 15s for at least one post container to appear
WebDriverWait(browser, 15).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed-shared-update-v2"))
)
print("Page loaded, beginning to scroll…")

# small human‐like pause before scrolling
time.sleep(random.uniform(1, 2))

company_name = page.rstrip("/").split("/")[-1].replace("-", " ").title()
print(f"Scraping posts for: {company_name}")

last_height = browser.execute_script("return document.body.scrollHeight")
no_change_count = 0
scrolls = 0

while no_change_count < 3 and scrolls < MAX_SCROLLS:
    browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    pause = SCROLL_PAUSE + random.uniform(0.5, 2.0)
    time.sleep(pause)
    new_height = browser.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        no_change_count += 1
    else:
        no_change_count, last_height = 0, new_height
    scrolls += 1
print(f"Done scrolling after {scrolls} iterations")

# ----------------------------
# Parse page and extract containers
# ----------------------------
linkedin_soup = bs(browser.page_source, "html.parser")

containers = [
    c for c in linkedin_soup.find_all("div", {"class": "feed-shared-update-v2"})
    if c.get("data-urn", "").startswith("activity")
][:MAX_POSTS]  # cap to MAX_POSTS

# ----------------------------
# Helper functions
# ----------------------------
def get_actual_date(date_str):
    today = datetime.today().strftime("%Y-%m-%d")
    def get_past_date(days=0, weeks=0, months=0, years=0):
        dt = datetime.strptime(today, "%Y-%m-%d") - relativedelta(
            days=days, weeks=weeks, months=months, years=years)
        return dt.strftime("%Y-%m-%d")

    if "hour" in date_str:
        return today
    if "day" in date_str:
        return get_past_date(days=int(date_str.split()[0]))
    if "week" in date_str:
        return get_past_date(weeks=int(date_str.split()[0]))
    if "month" in date_str:
        return get_past_date(months=int(date_str.split()[0]))
    if "year" in date_str:
        return get_past_date(years=int(date_str.split()[0]))

    parts = date_str.split("-")
    if len(parts) == 2:
        m, d = parts
        return f"{datetime.today().year}-{m.zfill(2)}-{d.zfill(2)}"
    if len(parts) == 3:
        return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
    return date_str

def convert_abbreviated_to_number(s):
    if "K" in s:
        return int(float(s.replace("K", "")) * 1_000)
    if "M" in s:
        return int(float(s.replace("M", "")) * 1_000_000)
    try:
        return int(s)
    except:
        return 0

def get_media_info(container):
    candidates = [
        ("div", {"class": "update-components-video"}, "Video"),
        ("div", {"class": "update-components-linkedin-video"}, "Video"),
        ("div", {"class": "update-components-image"}, "Image"),
        ("article", {"class": "update-components-article"}, "Article"),
        ("div", {"class": "feed-shared-external-video__meta"}, "YouTube Video"),
        ("div", {"class": "feed-shared-mini-update-v2 feed-shared-update-v2__update-content-wrapper artdeco-card"}, "Shared Post"),
        ("div", {"class": "feed-shared-poll ember-view"}, "Poll/Other")
    ]
    for tag, attrs, mtype in candidates:
        el = container.find(tag, attrs)
        if el:
            a = el.find("a", href=True)
            return (a["href"] if a else "None", mtype)
    return ("None", "Unknown")

# ----------------------------
# Scrape posts into list
# ----------------------------
posts_data = []
for container in containers:
    # text
    text_el = container.find("div", {"class": "feed-shared-update-v2__description-wrapper"})
    post_text = text_el.get_text(strip=True) if text_el else ""

    # media
    media_link, media_type = get_media_info(container)

    # date
    date_el = container.find("div", {"class": "ml4 mt2 text-body-xsmall t-black--light"})
    raw_date = date_el.get_text(strip=True) if date_el else ""
    post_date = get_actual_date(raw_date)

    # reactions/comments/shares
    btns = lambda keyword: container.find_all(
        lambda t: t.name=="button" and "aria-label" in t.attrs and keyword in t["aria-label"].lower()
    )
    reaction_buttons = btns("reaction")
    post_reactions = reaction_buttons[1].text.strip() if len(reaction_buttons)>1 else (reaction_buttons[0].text.strip() if reaction_buttons else "0")

    comment_buttons = btns("comment")
    post_comments = comment_buttons[1].text.strip() if len(comment_buttons)>1 else (comment_buttons[0].text.strip() if comment_buttons else "0")

    share_buttons = btns("repost")
    post_shares = share_buttons[1].text.strip() if len(share_buttons)>1 else (share_buttons[0].text.strip() if share_buttons else "0")

    posts_data.append({
        "Page": company_name,
        "Date": post_date,
        "Post Text": post_text,
        "Media Type": media_type,
        "Likes": post_reactions,
        "Comments": post_comments,
        "Shares": post_shares,
        "Likes Numeric": convert_abbreviated_to_number(post_reactions),
        "Media Link": media_link
    })

# ----------------------------
# Build DataFrame, sort & export
# ----------------------------
df = pd.DataFrame(posts_data)
df.sort_values(by="Likes Numeric", ascending=False, inplace=True)

csv_file = f"{company_name}_posts.csv"
df.to_csv(csv_file, index=False, encoding="utf-8")
print(f"Data exported to {csv_file}")
