"""Script to generate a daily blog post using the local Llama 3 model."""

from app import db, BlogPost, generate_text


def create_daily_post():
    content = generate_text("Write a short daily blog post about Judaism.")
    title = content.split("\n")[0].strip()
    post = BlogPost(title=title, content=content)
    db.session.add(post)
    db.session.commit()
    print(f"Generated post: {title}")


if __name__ == "__main__":
    create_daily_post()
