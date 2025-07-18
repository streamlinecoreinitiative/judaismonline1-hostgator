"""Script to generate a daily blog post using the local Llama 3 model."""

from app import db, BlogPost, generate_blog_post


def create_daily_posts(count: int = 2):
    for _ in range(count):
        title, content = generate_blog_post()
        post = BlogPost(title=title, content=content)
        db.session.add(post)
        db.session.commit()
        print(f"Generated post: {title}")


if __name__ == "__main__":
    create_daily_posts()
