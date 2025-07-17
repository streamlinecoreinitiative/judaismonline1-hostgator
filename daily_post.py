"""Script to generate a daily blog post using the local Llama 3 model."""

from app import db, BlogPost, generate_blog_content


def create_daily_posts(count: int = 2):
    for _ in range(count):
        content = generate_blog_content()
        title = content.split("\n")[0].strip()
        post = BlogPost(title=title, content=content)
        db.session.add(post)
        db.session.commit()
        print(f"Generated post: {title}")


if __name__ == "__main__":
    create_daily_posts()
