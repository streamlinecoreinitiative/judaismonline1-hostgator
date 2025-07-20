import datetime
import os
from io import BytesIO
import smtplib
from email.message import EmailMessage

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

from cryptography.fernet import Fernet
import ollama
from markdown import markdown
import random
import requests
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import subprocess

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['GENERATING_STATIC'] = False
app.config['SHOW_LOGIN'] = True
app.secret_key = os.environ.get('SECRET_KEY', 'secret')
db = SQLAlchemy(app)

# Encryption key used to protect personal information
_key = os.environ.get('ENCRYPT_KEY')
if not _key:
    _key = Fernet.generate_key()
fernet = Fernet(_key)


# Markdown filter to render AI-generated text nicely
@app.template_filter('markdown')
def markdown_filter(text: str) -> str:
    """Convert Markdown text to HTML."""
    return markdown(text or '')

# Simple helpers to encrypt and decrypt text
def encrypt(text: str) -> bytes:
    if not text:
        return None
    return fernet.encrypt(text.encode())


def decrypt(token: bytes) -> str:
    if not token:
        return ''
    return fernet.decrypt(token).decode()


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


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200))
    option_b = db.Column(db.String(200))
    option_c = db.Column(db.String(200))
    option_d = db.Column(db.String(200))
    answer = db.Column(db.String(1))
    order = db.Column(db.Integer)

    course = db.relationship(
        "Course", backref=db.backref("quiz_questions", order_by="QuizQuestion.order")
    )


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


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    email = db.Column(db.String(200))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)




class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text)


def get_setting(key: str, default: str | None = None) -> str | None:
    setting = SiteSetting.query.filter_by(key=key).first()
    return setting.value if setting else default


def set_setting(key: str, value: str) -> None:
    setting = SiteSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = SiteSetting(key=key, value=value)
        db.session.add(setting)
    db.session.commit()


def require_login():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
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


def parse_json_response(text: str):
    """Try to parse JSON from a model response."""
    import json
    import re

    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    # Extract JSON from within a Markdown style code block
    match = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
    if match:
        snippet = match.group(1)
        try:
            return json.loads(snippet)
        except Exception:
            pass

    # Fallback: grab first JSON-looking portion
    match = re.search(r"[{\[].*[}\]]", text, re.DOTALL)
    if match:
        snippet = match.group(0)
        try:
            return json.loads(snippet)
        except Exception:
            pass
    return None


def generate_certificate_pdf(name: str, course: str, score: int) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(300, 720, "Certificate of Completion")
    c.setFont("Helvetica", 16)
    c.drawCentredString(300, 680, f"Awarded to {name}")
    c.drawCentredString(300, 650, f"Course: {course}")
    c.drawCentredString(300, 620, f"Score: {score}")
    c.drawCentredString(300, 590, datetime.date.today().strftime("%B %d, %Y"))
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()


def send_email(to_addr: str, subject: str, body: str, attachment: bytes | None = None) -> None:
    msg = EmailMessage()
    sender = get_setting("admin_email") or os.environ.get("ADMIN_EMAIL")
    if not sender:
        return
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        msg.add_attachment(attachment, maintype="application", subtype="pdf", filename="certificate.pdf")
    server = os.environ.get("SMTP_SERVER")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    if server:
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)


def clean_module_content(html: str, title: str) -> str:
    """Remove extraneous text and add a heading if missing."""
    import re

    # Remove references to next modules that the model occasionally adds
    html = re.sub(r"(?i)next module.*", "", html)

    # Strip any leading mentions of HTML or "HTML Lesson" phrases
    html = re.sub(r"(?i)^\s*HTML(?:\s*Lesson)?\s*[:\-]?\s*", "", html)

    # Ensure the module starts with a heading matching the title
    if title and not re.search(r"<h\d", html):
        html = f"<h2>{title}</h2>\n" + html

    return html.strip()


def generate_section_titles(topic: str, count: int = 3):
    """Return a list of module titles for the course."""
    prompt = (
        f"Provide {count} concise module titles for a course about {topic}. "
        "Respond in JSON as a simple list of strings."
    )
    data = parse_json_response(generate_text(prompt)) or []
    titles = [str(t) for t in data][:count]
    if not titles:
        titles = [f"Module {i}" for i in range(1, count + 1)]
    return titles


def generate_module_content(course_topic: str, module_title: str) -> str:
    """Generate detailed HTML content for a single module."""
    prompt = (
        f"Write an in-depth lesson formatted in HTML for a course about {course_topic}. "
        f"The module is titled '{module_title}'. Respond only with the HTML markup "
        "for the lesson and do not mention that it is HTML."
    )
    content = generate_text(prompt).strip()
    return clean_module_content(content, module_title)


def generate_course_sections(topic: str, count: int = 3):
    """Return a list of section dicts with title and content."""
    titles = generate_section_titles(topic, count)
    sections = []
    for i, title in enumerate(titles, 1):
        content = generate_module_content(topic, title)
        sections.append({"title": title, "content": content, "order": i})
    return sections


def generate_quiz_questions(topic: str, count: int = 10):
    """Return a list of quiz question dicts."""
    prompt = (
        f"Create {count} multiple choice quiz questions summarizing key points about {topic}. "
        "Provide options A, B, C and D and the correct answer letter. "
        "Respond in JSON with a list of objects having 'question', 'a', 'b', 'c', 'd' and 'answer'."
    )
    data = parse_json_response(generate_text(prompt))
    if not data:
        return []
    questions = []
    for i, item in enumerate(data, 1):
        questions.append({
            "question": item.get("question", ""),
            "a": item.get("a", ""),
            "b": item.get("b", ""),
            "c": item.get("c", ""),
            "d": item.get("d", ""),
            "answer": item.get("answer", "").strip().upper(),
            "order": i,
        })
    return questions


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
    # Keep only the 25 most recent items
    old_items = (
        NewsItem.query.order_by(NewsItem.created_at.desc())
        .offset(25)
        .all()
    )
    for item in old_items:
        db.session.delete(item)
    if old_items:
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
    # Initialize or update basic pages with richer default text
    default_pages = {
        "landing": (
            "Welcome to Judaism Online!\n\n"
            "## Our Mission\n"
            "Judaism Online is dedicated to making the wisdom of Judaism accessible to everyone. "
            "Through free articles, engaging courses and a welcoming community, we provide reliable "
            "resources for anyone curious about Jewish life and tradition.\n\n"
            "## What You'll Find\n"
            "- Weekly articles exploring Jewish thought and practice\n"
            "- Self-paced courses for beginners and advanced students\n"
            "- Resources geared toward those considering conversion\n"
            "- An open community forum for questions and discussion\n\n"
            "## Join Us\n"
            "Subscribe to our newsletter and follow us on social media to hear about new lessons, "
            "upcoming events and the latest happenings across the Jewish world.\n\n"
            "## Featured Topics\n"
            "From ancient biblical history to modern Jewish ethics, our articles cover a wide "
            "spectrum of subjects that help deepen your understanding of faith and tradition.\n\n"
            "## Stay Connected\n"
            "Sign up for our monthly bulletin for curated resources, upcoming webinars and community "
            "spotlights. We value your privacy and will never share your information."
        ),
        "about": (
            "Judaism Online grew out of a passion for sharing authentic Jewish knowledge with anyone "
            "seeking to learn. Our team brings together educators from diverse backgrounds to curate "
            "approachable content rooted in classical sources.\n\n"
            "The site offers weekly blog posts, carefully designed courses and news updates from across "
            "the Jewish world. Whether you're exploring Judaism for the first time or deepening long-held "
            "traditions, we aim to provide tools for meaningful growth.\n\n"
            "**Get involved:**\n"
            "- Read our latest [blog posts](/blog/) and share your thoughts.\n"
            "- Enroll in our [online courses](/courses/) to learn at your own pace.\n"
            "- Contact us with suggestions or questions — we welcome your feedback.\n\n"
            "## Our Approach\n"
            "We balance respect for tradition with an inclusive perspective. Every article and course is "
            "reviewed to ensure accuracy while remaining accessible to readers from any background.\n\n"
            "## Our History\n"
            "Judaism Online began as a small newsletter shared among friends who loved studying Torah together. "
            "Over the years it has grown into an online destination for learners around the world seeking clear "
            "explanations and inspirational teachings.\n\n"
            "## Meet the Team\n"
            "Our contributors include rabbis, educators and passionate community members. Each writer brings a "
            "unique voice while sharing the same goal: to make Jewish wisdom approachable and engaging for everyone."
        ),
        "contact": (
            "We would love to hear from you. For general inquiries please email "
            "[info@judaismonline.example](mailto:info@judaismonline.example). "
            "You can also reach us on social media or by using the form below.\n\n"
            "**Mailing address:**\n"
            "Judaism Online\n"
            "123 Learning Lane\n"
            "Springfield, USA\n\n"
            "Follow us on your favorite social media platforms for the latest articles and community discussions. "
            "You can find us on Facebook, Instagram and Twitter under the username **@JudaismOnline**.\n\n"
            "We try to respond to all messages within two business days. Your questions and suggestions help us "
            "improve the site for everyone."
        ),
        "faq": (
            "### What is Judaism Online?\n"
            "Judaism Online is a free educational site offering articles, classes and news about Jewish life and tradition.\n\n"
            "### Do I need any prior knowledge?\n"
            "No prior background is required. Our beginner courses are designed for newcomers and those exploring conversion.\n\n"
            "### Is the content free?\n"
            "Yes. All articles and courses currently published on Judaism Online are available at no cost.\n\n"
            "### Can I suggest a topic?\n"
            "Absolutely! We welcome new ideas for articles and lessons. Use the contact form to send us your suggestions.\n\n"
            "### How often is new content added?\n"
            "We post new blog entries weekly and regularly expand our course offerings throughout the year.\n\n"
            "### How do I enroll in a course?\n"
            "Browse our course catalog and click the enrollment link on the course page. You'll receive email instructions for "
            "accessing lessons and tracking your progress.\n\n"
            "### Do you host live events?\n"
            "Yes. We periodically offer webinars and virtual Q&A sessions with guest teachers. Event details are posted on our "
            "homepage and social media channels."
        ),
        "terms": (
            "## Terms and Disclaimer\n"
            "Any personal details you provide remain private and are used only to "
            "run the site and send optional updates. All courses and articles are "
            "offered free of charge. Certificates are also free, though you may "
            "choose to contribute a small fee to help support the site's operating "
            "costs. We never share your information.\n\n"
            "### Disclaimer\n"
            "Some content is generated with local AI models and may contain errors. "
            "Always consult qualified authorities when making important decisions."
        ),
    }
    for slug, content in default_pages.items():
        page = Page.query.filter_by(slug=slug).first()
        if page is None:
            db.session.add(Page(slug=slug, title=slug.capitalize(), content=content))
        else:
            page.content = content
    db.session.commit()
    if not get_setting("admin_email") and os.environ.get("ADMIN_EMAIL"):
        set_setting("admin_email", os.environ.get("ADMIN_EMAIL"))


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


@app.route("/contact/", methods=["GET", "POST"])
def contact():
    page = Page.query.filter_by(slug="contact").first()
    sent = False
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        if message:
            db.session.add(ContactMessage(name=name, email=email, message=message))
            db.session.commit()
            sent = True
    return render_template("contact.html", page=page, sent=sent)


@app.route("/faq/")
def faq():
    page = Page.query.filter_by(slug="faq").first()
    return render_template("page.html", page=page)


@app.route("/terms/")
def terms():
    page = Page.query.filter_by(slug="terms").first()
    return render_template("page.html", page=page)


@app.route("/news/")
def news():
    items = (
        NewsItem.query.order_by(NewsItem.created_at.desc())
        .limit(25)
        .all()
    )
    return render_template("news.html", items=items)


@app.route("/login/", methods=["GET", "POST"])
def login():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
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
    quiz_passed = session.get("quiz_passed", {}).get(str(course_id))
    return render_template(
        "course_detail.html",
        course=course,
        sections=sections,
        completed=completed,
        all_done=all_done,
        quiz_passed=quiz_passed,
        can_download=all_done and quiz_passed,
    )


@app.route("/certificate/<int:course_id>/", methods=["GET", "POST"])
def certificate(course_id):
    course = Course.query.get_or_404(course_id)
    sections = (
        CourseSection.query.filter_by(course_id=course_id)
        .order_by(CourseSection.order)
        .all()
    )
    completed = session.get("completed_sections", {}).get(str(course_id), [])
    quiz_passed = session.get("quiz_passed", {}).get(str(course_id))
    if sections and not all(s.id in completed for s in sections):
        abort(403)
    if not quiz_passed:
        abort(403)
    name = None
    sent = False
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        score = session.get("quiz_scores", {}).get(str(course_id), 0)
        if name and email:
            pdf = generate_certificate_pdf(name, course.title, score)
            send_email(
                email,
                f"Your {course.title} certificate",
                "Congratulations on completing the course!",
                pdf,
            )
            sent = True
    return render_template(
        "certificate.html", course=course, sections=sections, name=name, sent=sent
    )


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
        if section.question and section.answer:
            answer = request.form.get("answer", "").strip().lower()
            if answer == section.answer.strip().lower():
                completed.append(section_id)
        else:
            if request.form.get("complete"):
                completed.append(section_id)
        if section_id not in completed:
            return render_template(
                "course_section.html",
                course=course,
                section=section,
                completed=False,
                error=True,
            )
        session.setdefault("completed_sections", {})[str(course_id)] = completed
        session.modified = True
        return redirect(url_for("course_detail", course_id=course_id))
    return render_template(
        "course_section.html",
        course=course,
        section=section,
        completed=section_id in completed,
        error=False,
    )


@app.route("/courses/<int:course_id>/quiz/", methods=["GET", "POST"])
def course_quiz(course_id):
    course = Course.query.get_or_404(course_id)
    questions = (
        QuizQuestion.query.filter_by(course_id=course_id)
        .order_by(QuizQuestion.order)
        .all()
    )
    score = None
    passed = session.get("quiz_passed", {}).get(str(course_id))
    stored_scores = session.get("quiz_scores", {})
    if str(course_id) in stored_scores:
        score = stored_scores[str(course_id)]
    if request.method == "POST":
        correct = 0
        for q in questions:
            answer = request.form.get(str(q.id), "").upper()
            if answer == q.answer:
                correct += 1
        score = correct
        session.setdefault("quiz_scores", {})[str(course_id)] = correct
        passed = correct >= 8
        if passed:
            session.setdefault("quiz_passed", {})[str(course_id)] = True
        session.modified = True
    return render_template(
        "course_quiz.html",
        course=course,
        questions=questions,
        score=score,
        passed=passed,
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
            module_count = min(int(request.form.get("module_count", 3)), 10)
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
            for sec in generate_course_sections(topic, module_count):
                section = CourseSection(
                    course_id=course.id,
                    title=sec["title"],
                    content=sec["content"],
                    order=sec["order"],
                )
                db.session.add(section)
            db.session.commit()
            # Generate quiz questions for the course
            for q in generate_quiz_questions(topic, 10):
                question = QuizQuestion(
                    course_id=course.id,
                    question=q["question"],
                    option_a=q["a"],
                    option_b=q["b"],
                    option_c=q["c"],
                    option_d=q["d"],
                    answer=q["answer"],
                    order=q["order"],
                )
                db.session.add(question)
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
        elif action == "update_section":
            section = CourseSection.query.get_or_404(request.form.get("id"))
            section.title = request.form.get("title")
            section.content = request.form.get("content")
            section.question = request.form.get("question")
            section.answer = request.form.get("answer")
            db.session.commit()
        elif action == "delete_section":
            section = CourseSection.query.get_or_404(request.form.get("id"))
            db.session.delete(section)
            db.session.commit()
        elif action == "update_question":
            q = QuizQuestion.query.get_or_404(request.form.get("id"))
            q.question = request.form.get("question")
            q.option_a = request.form.get("a")
            q.option_b = request.form.get("b")
            q.option_c = request.form.get("c")
            q.option_d = request.form.get("d")
            q.answer = request.form.get("answer")
            db.session.commit()
        elif action == "delete_question":
            q = QuizQuestion.query.get_or_404(request.form.get("id"))
            db.session.delete(q)
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
        elif action == "push":
            subprocess.run(["python", "freeze.py"], check=True)
            subprocess.run(["git", "add", "docs"], check=True)
            msg = f"Update site {datetime.date.today().isoformat()}"
            subprocess.run(["git", "commit", "-m", msg])
            subprocess.run(["git", "push"])
        return redirect(url_for("admin"))
    pages = Page.query.all()
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    courses = Course.query.all()
    items = NewsItem.query.all()
    return render_template(
        "admin.html",
        pages=pages,
        posts=posts,
        courses=courses,
        items=items,
    )


if __name__ == "__main__":
    with app.app_context():
        create_tables()
    app.run(debug=True)
