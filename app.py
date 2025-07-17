import datetime
import os

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    abort,
)
from flask_sqlalchemy import SQLAlchemy
import ollama
import random
import requests

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'secret')
db = SQLAlchemy(app)


class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    prerequisites = db.Column(db.Text)


class Page(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)


class NewsItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


def require_login():
    if not session.get("logged_in"):
        return redirect(url_for("login"))


def generate_text(prompt: str) -> str:
    """Generate text from the local Llama 3 model via ollama."""
    stream = ollama.chat(
        model="llama3:8b",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    return "".join(chunk["message"]["content"] for chunk in stream)


NEWS_API_URL = "https://www.jta.org/wp-json/wp/v2/posts?per_page=5"


def generate_blog_content() -> str:
    """Create blog content using a random news topic when available."""
    topic = None
    try:
        resp = requests.get(NEWS_API_URL, timeout=10)
        resp.raise_for_status()
        items = resp.json()
        if items:
            topic = random.choice(items).get("title", {}).get("rendered")
    except Exception:
        topic = None

    date = datetime.datetime.utcnow().strftime("%B %d, %Y")
    if topic:
        prompt = (
            f"Write a short blog post about Judaism inspired by this news topic: {topic}. "
            f"Include today's date ({date}) in the text and do not mention the day of the week."
        )
    else:
        prompt = (
            f"Write a short blog post about an aspect of Judaism. "
            f"Include today's date ({date}) in the text and do not mention the day of the week."
        )
    return generate_text(prompt)


def create_tables():
    """Create database tables if they don't exist."""
    db.create_all()
    # Initialize default editable pages
    default_pages = {
        "landing": "Welcome to Judaism Online!",
        "about": "About us placeholder text.",
        "contact": "Contact information placeholder.",
        "faq": "Frequently asked questions placeholder.",
    }
    for slug, content in default_pages.items():
        page = Page.query.filter_by(slug=slug).first()
        if page is None:
            db.session.add(Page(slug=slug, title=slug.capitalize(), content=content))
    db.session.commit()


@app.route("/")
def index():
    page = Page.query.filter_by(slug="landing").first()
    return render_template("index.html", page=page)


@app.route("/blog/")
def blog():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template("blog.html", posts=posts)


@app.route("/courses/")
def courses():
    courses = Course.query.all()
    return render_template("courses.html", courses=courses)


@app.route("/about/")
def about():
    page = Page.query.filter_by(slug="about").first()
    return render_template("page.html", page=page)


@app.route("/contact/")
def contact():
    page = Page.query.filter_by(slug="contact").first()
    return render_template("page.html", page=page)


@app.route("/faq/")
def faq():
    page = Page.query.filter_by(slug="faq").first()
    return render_template("page.html", page=page)


@app.route("/news/")
def news():
    items = NewsItem.query.order_by(NewsItem.created_at.desc()).all()
    return render_template("news.html", items=items)


@app.route("/login/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == os.environ.get("ADMIN_PASSWORD", "bere"):
            session["logged_in"] = True
            return redirect(url_for("admin"))
    return render_template("login.html")


@app.route("/logout/")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("index"))


@app.route("/courses/<int:course_id>/")
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template("course_detail.html", course=course)


@app.route("/certificate/<int:course_id>/")
def certificate(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template("certificate.html", course=course)


@app.route("/admin/", methods=["GET", "POST"])
def admin():
    require_login()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "blog":
            content = generate_blog_content()
            title = content.split("\n")[0].strip()
            post = BlogPost(title=title, content=content)
            db.session.add(post)
            db.session.commit()
        elif action == "update_blog":
            post = BlogPost.query.get_or_404(request.form.get("id"))
            post.title = request.form.get("title")
            post.content = request.form.get("content")
            db.session.commit()
        elif action == "delete_blog":
            post = BlogPost.query.get_or_404(request.form.get("id"))
            db.session.delete(post)
            db.session.commit()
        elif action == "course":
            topic = request.form.get("topic", "Judaism")
            difficulty = request.form.get("difficulty", "Beginner")
            prerequisites = request.form.get("prerequisites", "")
            prompt = (
                f"Create a concise course outline on {topic} for those interested in converting to Judaism. "
                f"Focus on key concepts and steps."
            )
            description = generate_text(prompt)
            course = Course(
                title=topic,
                description=description,
                difficulty=difficulty,
                prerequisites=prerequisites,
            )
            db.session.add(course)
            db.session.commit()
        elif action == "update_course":
            course = Course.query.get_or_404(request.form.get("id"))
            course.title = request.form.get("title")
            course.description = request.form.get("description")
            course.difficulty = request.form.get("difficulty")
            course.prerequisites = request.form.get("prerequisites")
            db.session.commit()
        elif action == "delete_course":
            course = Course.query.get_or_404(request.form.get("id"))
            db.session.delete(course)
            db.session.commit()
        elif action == "update_news":
            item = NewsItem.query.get_or_404(request.form.get("id"))
            item.title = request.form.get("title")
            item.url = request.form.get("url")
            item.summary = request.form.get("summary")
            db.session.commit()
        elif action == "delete_news":
            item = NewsItem.query.get_or_404(request.form.get("id"))
            db.session.delete(item)
            db.session.commit()
        elif action == "page":
            slug = request.form.get("slug")
            content = request.form.get("content", "")
            page = Page.query.filter_by(slug=slug).first()
            if page:
                page.content = content
                db.session.commit()
        return redirect(url_for("admin"))
    pages = Page.query.all()
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    courses = Course.query.all()
    items = NewsItem.query.all()
    return render_template("admin.html", pages=pages, posts=posts, courses=courses, items=items)


if __name__ == "__main__":
    with app.app_context():
        create_tables()
    app.run(debug=True)
