import requests
from app import db, NewsItem

# Restrict to the Religion category so only faith-related news is stored.
API_URL = (
    "https://www.jta.org/wp-json/wp/v2/posts?categories=46947&per_page=5"
)

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
    # Use an application context so SQLAlchemy can access the database
    from app import app
    with app.app_context():
        fetch_news()
