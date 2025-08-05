import requests
from app import db, NewsItem, get_setting, DEFAULT_NEWS_API_URL

# Default feed used if no custom URL is configured.

def fetch_news():
    api_url = get_setting("news_api_url") or DEFAULT_NEWS_API_URL
    resp = requests.get(api_url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("results", data)
    for item in items:
        title = item.get("title", "")
        url = item.get("link") or item.get("url", "")
        summary = item.get("description", "")
        if not NewsItem.query.filter_by(url=url).first():
            db.session.add(NewsItem(title=title, url=url, summary=summary))
    db.session.commit()
    old_items = (
        NewsItem.query.order_by(NewsItem.created_at.desc())
        .offset(25)
        .all()
    )
    for item in old_items:
        db.session.delete(item)
    if old_items:
        db.session.commit()

if __name__ == "__main__":
    # Use an application context so SQLAlchemy can access the database
    from app import app
    with app.app_context():
        fetch_news()
