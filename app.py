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
        if password == os.environ.get("ADMIN_PASSWORD", "admin"):
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
            prompt = "Write a short daily blog post about Judaism."
            content = generate_text(prompt)
            title = content.split("\n")[0].strip()
            post = BlogPost(title=title, content=content)
            db.session.add(post)
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
        elif action == "page":
            slug = request.form.get("slug")
            content = request.form.get("content", "")
            page = Page.query.filter_by(slug=slug).first()
            if page:
                page.content = content
                db.session.commit()
        return redirect(url_for("admin"))
    pages = Page.query.all()
    return render_template("admin.html", pages=pages)


if __name__ == "__main__":
    with app.app_context():
        create_tables()
    app.run(debug=True)
