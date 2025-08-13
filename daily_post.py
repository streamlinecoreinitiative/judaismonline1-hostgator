"""Script to generate a daily blog post using the local Llama 3 model."""

import datetime
from app import db, BlogPost, generate_blog_post


def create_daily_posts(count: int = 2):
    # Check if there are posts from today
    today = datetime.date.today()
    existing_posts_today = BlogPost.query.filter(
        db.func.date(BlogPost.created_at) == today
    ).count()
    
    if existing_posts_today >= count:
        print(f"Already have {existing_posts_today} posts from today. Skipping generation.")
        return
    
    posts_to_create = count - existing_posts_today
    for _ in range(posts_to_create):
        title, content = generate_blog_post()
        post = BlogPost(title=title, content=content)
        db.session.add(post)
        db.session.commit()
        print(f"Generated post: {title}")


if __name__ == "__main__":
    from app import app, create_tables

    # Run within the Flask application context so database operations work
    with app.app_context():
        create_tables()
        create_daily_posts()
