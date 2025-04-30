# Import necessary libraries
import os
import time
import re
import pandas as pd
import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup as bs
from datetime import datetime
from dateutil.relativedelta import relativedelta

# LinkedIn Credentials from .env
username = os.getenv("LINKEDIN_USER")
password = os.getenv("LINKEDIN_PASS")
if not username or not password:
    raise RuntimeError("Please set LINKEDIN_USER and LINKEDIN_PASS in your environment.")

# Initialize stealth Chrome options
options = uc.ChromeOptions()
options.add_argument("--start-maximized")
# options.add_argument("--user-data-dir=/path/to/your/chrome/profile")  # optional profile isolation

# Launch a headful, undetected Chrome
browser = uc.Chrome(
    driver_executable_path=ChromeDriverManager().install(),
    options=options
)

# Set LinkedIn page URL for scraping
page = 'https://www.linkedin.com/company/nike'

# Open LinkedIn login page
browser.get('https://www.linkedin.com/login')
time.sleep(2)

# Enter login credentials and submit
browser.find_element(By.ID, "username").send_keys(username)
browser.find_element(By.ID, "password").send_keys(password)
browser.find_element(By.ID, "password").submit()
time.sleep(3)  # wait for post-login redirect

# Navigate to the company’s posts page
post_page = page + '/posts'
browser.get(post_page)
time.sleep(2)

# Extract company name from URL
company_name = page.rstrip('/').split('/')[-1].replace('-', ' ').title()
print(f"Scraping posts for: {company_name}")

# Scroll parameters
SCROLL_PAUSE_TIME = 1.5
last_height = browser.execute_script("return document.body.scrollHeight")
no_change_count = 0

# Scroll until no new content loads
while no_change_count < 3:
    browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(SCROLL_PAUSE_TIME)
    new_height = browser.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        no_change_count += 1
    else:
        no_change_count = 0
        last_height = new_height

# Parse the page source
linkedin_soup = bs(browser.page_source, "html.parser")

# (Optional) save raw HTML
with open(f"{company_name}_soup.txt", "w+", encoding="utf-8") as t:
    t.write(linkedin_soup.prettify())

# Find all post containers
containers = [
    c for c in linkedin_soup.find_all("div", {"class": "feed-shared-update-v2"})
    if c.get("data-urn", "").startswith("activity")
]

# Helper: convert relative dates to YYYY-MM-DD
def get_actual_date(date_str):
    today = datetime.today().strftime('%Y-%m-%d')
    def get_past_date(days=0, weeks=0, months=0, years=0):
        dt = datetime.strptime(today, '%Y-%m-%d') - relativedelta(
            days=days, weeks=weeks, months=months, years=years)
        return dt.strftime('%Y-%m-%d')

    if 'hour' in date_str:
        return today
    if 'day' in date_str:
        return get_past_date(days=int(date_str.split()[0]))
    if 'week' in date_str:
        return get_past_date(weeks=int(date_str.split()[0]))
    if 'month' in date_str:
        return get_past_date(months=int(date_str.split()[0]))
    if 'year' in date_str:
        return get_past_date(years=int(date_str.split()[0]))

    parts = date_str.split('-')
    if len(parts) == 2:
        m, d = parts
        m, d = m.zfill(2), d.zfill(2)
        return f"{datetime.today().year}-{m}-{d}"
    if len(parts) == 3:
        y, m, d = parts[2], parts[0].zfill(2), parts[1].zfill(2)
        return f"{y}-{m}-{d}"
    return date_str

# Helper: expand "1.2K" → 1200, etc.
def convert_abbreviated_to_number(s):
    if 'K' in s:
        return int(float(s.replace('K','')) * 1_000)
    if 'M' in s:
        return int(float(s.replace('M','')) * 1_000_000)
    try:
        return int(s)
    except:
        return 0

# Helper: media info
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
            a = el.find('a', href=True)
            return (a['href'] if a else "None", mtype)
    return ("None", "Unknown")

# Gather post data
posts_data = []
for container in containers:
    post_text = container.find(
        "div", {"class": "feed-shared-update-v2__description-wrapper"}
    ).get_text(strip=True) if container.find(
        "div", {"class": "feed-shared-update-v2__description-wrapper"}
    ) else ""

    media_link, media_type = get_media_info(container)

    raw_date = container.find(
        "div", {"class": "ml4 mt2 text-body-xsmall t-black--light"}
    ).get_text(strip=True) if container.find(
        "div", {"class": "ml4 mt2 text-body-xsmall t-black--light"}
    ) else ""
    post_date = get_actual_date(raw_date)

    # Reactions
    reaction_buttons = container.find_all(lambda t: t.name=='button' and
                                          'aria-label' in t.attrs and
                                          'reaction' in t['aria-label'].lower())
    idx = 1 if len(reaction_buttons)>1 else 0
    post_reactions = reaction_buttons[idx].text.strip() if reaction_buttons else "0"

    # Comments
    comment_buttons = container.find_all(lambda t: t.name=='button' and
                                         'aria-label' in t.attrs and
                                         'comment' in t['aria-label'].lower())
    idx = 1 if len(comment_buttons)>1 else 0
    post_comments = comment_buttons[idx].text.strip() if comment_buttons else "0"

    # Shares
    share_buttons = container.find_all(lambda t: t.name=='button' and
                                       'aria-label' in t.attrs and
                                       'repost' in t['aria-label'].lower())
    idx = 1 if len(share_buttons)>1 else 0
    post_shares = share_buttons[idx].text.strip() if share_buttons else "0"

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

# Build DataFrame, sort and export
df = pd.DataFrame(posts_data)
df.sort_values(by="Likes Numeric", ascending=False, inplace=True)

csv_file = f"{company_name}_posts.csv"
df.to_csv(csv_file, index=False, encoding='utf-8')
print(f"Data exported to {csv_file}")
