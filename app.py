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
from markdown import markdown
import random
import requests
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.secret_key = os.environ.get('SECRET_KEY', 'secret')
db = SQLAlchemy(app)


# Markdown filter to render AI-generated text nicely
@app.template_filter('markdown')
def markdown_filter(text: str) -> str:
    """Convert Markdown text to HTML."""
    return markdown(text or '')


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
    # Optional icon image filename stored in static/uploads
    icon = db.Column(db.String(200))


class CourseSection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    question = db.Column(db.Text)
    answer = db.Column(db.String(200))
    order = db.Column(db.Integer)

    course = db.relationship("Course", backref=db.backref("sections", order_by="CourseSection.order"))


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


# Only fetch posts from the "Religion" category to keep blog topics focused on
# religious news.
NEWS_API_URL = (
    "https://www.jta.org/wp-json/wp/v2/posts?categories=46947&per_page=5"
)


def generate_blog_post() -> tuple[str, str]:
    """Create a blog post and return a `(title, content)` tuple."""
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
            f"Include today's date ({date}) in the text and do not mention the day of the week. "
            "Start with a concise title summarizing the post on the first line, followed by a blank line and then the body."
        )
    else:
        prompt = (
            f"Write a short blog post about an aspect of Judaism. "
            f"Include today's date ({date}) in the text and do not mention the day of the week. "
            "Start with a concise title summarizing the post on the first line, followed by a blank line and then the body."
        )
    response = generate_text(prompt).strip()
    lines = response.split("\n", 1)
    title = lines[0].strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    return title, content


def generate_course_sections(topic: str, count: int = 3):
    """Return a list of section dicts with title, content, question and answer."""
    prompt = (
        f"Create {count} sections for a course about {topic}. "
        "For each section provide a title, detailed HTML content, one short multiple choice question with options A, B and C, and the correct answer letter. "
        "Respond in JSON with a list of objects having 'title', 'content', 'question' and 'answer'."
    )
    import json
    try:
        data = json.loads(generate_text(prompt))
    except Exception:
        return []
    sections = []
    for i, item in enumerate(data, 1):
        sections.append({
            "title": item.get("title", f"Section {i}"),
            "content": item.get("content", ""),
            "question": item.get("question", ""),
            "answer": item.get("answer", "").strip(),
            "order": i,
        })
    return sections


def fetch_news_items() -> None:
    """Fetch latest news from the API and store new items."""
    resp = requests.get(NEWS_API_URL, timeout=10)
    resp.raise_for_status()
    for item in resp.json():
        title = item.get("title", {}).get("rendered", "")
        url = item.get("link", "")
        summary = item.get("excerpt", {}).get("rendered", "")
        if not NewsItem.query.filter_by(url=url).first():
            db.session.add(NewsItem(title=title, url=url, summary=summary))
    db.session.commit()


def create_tables():
    """Create database tables if they don't exist."""
    db.create_all()
    # Ensure uploads folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # Add icon column to Course if missing
    inspector = inspect(db.engine)
    cols = [c['name'] for c in inspector.get_columns('course')]
    if 'icon' not in cols:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE course ADD COLUMN icon VARCHAR(200)'))
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
    sections = (
        CourseSection.query.filter_by(course_id=course_id)
        .order_by(CourseSection.order)
        .all()
    )
    completed = session.get("completed_sections", {}).get(str(course_id), [])
    all_done = sections and all(s.id in completed for s in sections)
    return render_template(
        "course_detail.html",
        course=course,
        sections=sections,
        completed=completed,
        all_done=all_done,
    )


@app.route("/certificate/<int:course_id>/")
def certificate(course_id):
    course = Course.query.get_or_404(course_id)
    sections = CourseSection.query.filter_by(course_id=course_id).all()
    completed = session.get("completed_sections", {}).get(str(course_id), [])
    if sections and not all(s.id in completed for s in sections):
        abort(403)
    return render_template("certificate.html", course=course)


@app.route("/courses/<int:course_id>/full/")
def course_full(course_id):
    """Display the entire course with all sections in one page."""
    course = Course.query.get_or_404(course_id)
    sections = (
        CourseSection.query.filter_by(course_id=course_id)
        .order_by(CourseSection.order)
        .all()
    )
    return render_template("course_full.html", course=course, sections=sections)


@app.route("/courses/<int:course_id>/section/<int:section_id>/", methods=["GET", "POST"])
def course_section(course_id, section_id):
    course = Course.query.get_or_404(course_id)
    section = CourseSection.query.get_or_404(section_id)
    completed = session.get("completed_sections", {}).get(str(course_id), [])
    if request.method == "POST":
        answer = request.form.get("answer", "").strip().lower()
        if answer == section.answer.strip().lower():
            completed.append(section_id)
            session.setdefault("completed_sections", {})[str(course_id)] = completed
            session.modified = True
            return redirect(url_for("course_detail", course_id=course_id))
    return render_template(
        "course_section.html",
        course=course,
        section=section,
        completed=section_id in completed,
    )


@app.route("/admin/", methods=["GET", "POST"])
def admin():
    require_login()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "blog":
            title, content = generate_blog_post()
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
            description = request.form.get("description", "").strip()
            file = request.files.get("icon")
            icon_name = None
            if file and file.filename:
                os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                icon_name = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], icon_name))
            if not description:
                prompt = (
                    f"Create a detailed, comprehensive course on {topic} for those interested in converting to Judaism. "
                    f"Provide extensive explanations, historical context and practical guidance in HTML format so it can be displayed on a web page."
                )
                description = generate_text(prompt)
            course = Course(
                title=topic,
                description=description,
                difficulty=difficulty,
                prerequisites=prerequisites,
                icon=icon_name,
            )
            db.session.add(course)
            db.session.commit()
            # Generate sections using the AI and store them
            for sec in generate_course_sections(topic):
                section = CourseSection(
                    course_id=course.id,
                    title=sec["title"],
                    content=sec["content"],
                    question=sec["question"],
                    answer=sec["answer"],
                    order=sec["order"],
                )
                db.session.add(section)
            db.session.commit()
        elif action == "update_course":
            course = Course.query.get_or_404(request.form.get("id"))
            course.title = request.form.get("title")
            course.description = request.form.get("description")
            course.difficulty = request.form.get("difficulty")
            course.prerequisites = request.form.get("prerequisites")
            if request.form.get("remove_icon"):
                if course.icon:
                    try:
                        os.remove(os.path.join(app.config["UPLOAD_FOLDER"], course.icon))
                    except Exception:
                        pass
                course.icon = None
            file = request.files.get("icon")
            if file and file.filename:
                os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                if course.icon:
                    try:
                        os.remove(os.path.join(app.config["UPLOAD_FOLDER"], course.icon))
                    except Exception:
                        pass
                icon_name = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], icon_name))
                course.icon = icon_name
            db.session.commit()
        elif action == "delete_course":
            course = Course.query.get_or_404(request.form.get("id"))
            db.session.delete(course)
            db.session.commit()
        elif action == "fetch_news":
            fetch_news_items()
        elif action == "create_news":
            title = request.form.get("title", "")
            url = request.form.get("url", "")
            summary = request.form.get("summary", "")
            if title and url:
                db.session.add(NewsItem(title=title, url=url, summary=summary))
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
