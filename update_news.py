import requests
from app import db, NewsItem

API_URL = "https://www.jta.org/wp-json/wp/v2/posts?per_page=5"

def fetch_news():
    resp = requests.get(API_URL, timeout=10)
    resp.raise_for_status()
    for item in resp.json():
        title = item.get("title", {}).get("rendered", "")
        url = item.get("link", "")
        summary = item.get("excerpt", {}).get("rendered", "")
        if not NewsItem.query.filter_by(url=url).first():
            db.session.add(NewsItem(title=title, url=url, summary=summary))
    db.session.commit()

if __name__ == "__main__":
    fetch_news()
