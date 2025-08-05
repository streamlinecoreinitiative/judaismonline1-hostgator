import datetime
import os
import sys
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
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import stripe

from cryptography.fernet import Fernet
import ollama
from markdown import markdown
from bs4 import BeautifulSoup
import random
import requests
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import subprocess

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://beregrond:Caco101268123456!!@monroyasesores.com.mx/monroyas_education",
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["GENERATING_STATIC"] = False
app.config["SHOW_LOGIN"] = os.environ.get("SHOW_LOGIN") == "1"
app.secret_key = os.environ.get("SECRET_KEY", "secret")
db = SQLAlchemy(app)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# Encryption key used to protect personal information
_key = os.environ.get("ENCRYPT_KEY")
if not _key:
    _key = Fernet.generate_key()
fernet = Fernet(_key)


# Markdown filter to render AI-generated text nicely
@app.template_filter("markdown")
def markdown_filter(text: str) -> str:
    """Convert Markdown text to sanitized HTML."""
    html = markdown(text or "", extensions=["extra"])
    return str(BeautifulSoup(html, "html.parser"))


# Simple helpers to encrypt and decrypt text
def encrypt(text: str) -> bytes:
    if not text:
        return None
    return fernet.encrypt(text.encode())


def decrypt(token: bytes) -> str:
    if not token:
        return ""
    return fernet.decrypt(token).decode()


class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_company_admin = db.Column(db.Boolean, default=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"))
    company = db.relationship("Company", backref="users")


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    prerequisites = db.Column(db.Text)
    # Optional icon image filename stored in static/uploads
    icon = db.Column(db.String(200))
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"))
    company = db.relationship("Company", backref="courses")
    price_cents = db.Column(db.Integer, default=0)


class CourseSection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer,
        db.ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    question = db.Column(db.Text)
    answer = db.Column(db.String(200))
    order = db.Column(db.Integer)

    course = db.relationship(
        "Course",
        backref=db.backref(
            "sections",
            order_by="CourseSection.order",
            cascade="all, delete-orphan",
        ),
    )


class SectionProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey("course_section.id"), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    user = db.relationship("User", backref="progress")
    section = db.relationship("CourseSection", backref="progress")
    __table_args__ = (db.UniqueConstraint("user_id", "section_id", name="uix_user_section"),)


class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    paid = db.Column(db.Boolean, default=False)
    user = db.relationship("User", backref="enrollments")
    course = db.relationship("Course", backref="enrollments")
    __table_args__ = (db.UniqueConstraint("user_id", "course_id", name="uix_user_course"),)


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer,
        db.ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
    )
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200))
    option_b = db.Column(db.String(200))
    option_c = db.Column(db.String(200))
    option_d = db.Column(db.String(200))
    answer = db.Column(db.String(1))
    order = db.Column(db.Integer)

    course = db.relationship(
        "Course",
        backref=db.backref(
            "quiz_questions",
            order_by="QuizQuestion.order",
            cascade="all, delete-orphan",
        ),
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


@app.context_processor
def inject_user():
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else None
    return {"current_user": user}


def user_has_course_access(course: Course, user_id: int | None) -> bool:
    """Check if a user can view a course."""
    # Company courses require membership and an assignment
    if course.company_id is not None:
        if not user_id:
            return False
        user = User.query.get(user_id)
        if not user or user.company_id != course.company_id:
            return False
        return (
            Enrollment.query.filter_by(user_id=user_id, course_id=course.id).first()
            is not None
        )
    # Paid open courses require an enrollment record
    if course.price_cents > 0:
        if not user_id:
            return False
        return (
            Enrollment.query.filter_by(
                user_id=user_id, course_id=course.id, paid=True
            ).first()
            is not None
        )
    # Free open courses are available to everyone
    return True


def require_course_access(course: Course):
    user_id = session.get("user_id")
    if not user_has_course_access(course, user_id):
        return redirect(url_for("course_detail", course_id=course.id))
    return None


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


# Default feed for the news section. Individual deployments can override this
# via the admin settings form.
DEFAULT_NEWS_API_URL = (
    "https://newsdata.io/api/1/news?language=es&category=business&apikey=YOUR_API_KEY"
)


def generate_blog_post() -> tuple[str, str]:
    """Create a blog post and return a ``(title, content)`` tuple."""
    topic = None
    news_api = get_setting("news_api_url") or DEFAULT_NEWS_API_URL
    try:
        resp = requests.get(news_api, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("results", [])
        if items:
            topic = random.choice(items).get("title")
    except Exception:
        topic = None

    site_topic = get_setting("site_topic", "recursos humanos")
    date = datetime.datetime.utcnow().strftime("%d/%m/%Y")
    if topic:
        prompt = (
            f"Escribe una breve entrada de blog sobre {site_topic} inspirada en esta noticia: {topic}. "
            f"Incluye la fecha de hoy ({date}) en el texto y no menciones el día de la semana. "
            "Comienza con un título conciso en la primera línea, seguido de un salto de línea y luego el cuerpo."
        )
    else:
        prompt = (
            f"Escribe una breve entrada de blog sobre algún aspecto de {site_topic}. "
            f"Incluye la fecha de hoy ({date}) en el texto y no menciones el día de la semana. "
            "Comienza con un título conciso en la primera línea, seguido de un salto de línea y luego el cuerpo."
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


def send_email(
    to_addr: str, subject: str, body: str, attachment: bytes | None = None
) -> None:
    msg = EmailMessage()
    sender = get_setting("admin_email") or os.environ.get("ADMIN_EMAIL")
    if not sender:
        return
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        msg.add_attachment(
            attachment,
            maintype="application",
            subtype="pdf",
            filename="certificate.pdf",
        )
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

    # Remove references to other modules that the model occasionally adds
    html = re.sub(r"(?i)(next\s+module|module\s+\d+).*", "", html)

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
        f"Write a lesson for a course about {course_topic}. "
        f"The module title is '{module_title}'. "
        "Format the response in HTML using a consistent structure: "
        "<h2>{module_title}</h2> as the heading, followed by a section titled 'Introduction', "
        "a section titled 'Main Content' covering the topic, and a final section titled 'Conclusion' summarizing the key points. "
        "Do not reference any other modules and respond only with the HTML markup."
    ).format(module_title=module_title)
    content = generate_text(prompt).strip()
    return clean_module_content(content, module_title)


def generate_course_overview(topic: str) -> str:
    """Return an HTML overview for the course."""
    prompt = (
        f"Write a concise overview for a course about {topic}. "
        "Format the response in HTML with three sections: "
        "<h2>Introduction</h2> describing the course, "
        "<h2>Main Content</h2> outlining what will be covered, and "
        "<h2>Learning Expectations</h2> summarising the outcomes. "
        "Do not mention how many modules the course has."
    )
    return generate_text(prompt).strip()


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
        "Respond only with valid JSON. The JSON must be a list of objects each containing "
        "'question', 'a', 'b', 'c', 'd' and 'answer'. Do not include any explanation or formatting outside the JSON."
    )
    data = None
    for _ in range(3):
        data = parse_json_response(generate_text(prompt))
        if data:
            break
    if not data:
        return []
    questions = []
    for i, item in enumerate(data, 1):
        questions.append(
            {
                "question": item.get("question", ""),
                "a": item.get("a", ""),
                "b": item.get("b", ""),
                "c": item.get("c", ""),
                "d": item.get("d", ""),
                "answer": item.get("answer", "").strip().upper(),
                "order": i,
            }
        )
    return questions


def generate_course_topics(topic: str, count: int = 3) -> list[str]:
    """Return a list of course titles related to ``topic``."""
    prompt = (
        f"Provide {count} concise course titles related to {topic}. "
        "Respond in JSON as a simple list of strings."
    )
    data = parse_json_response(generate_text(prompt)) or []
    titles = [str(t) for t in data][:count]
    if not titles:
        titles = [f"{topic} Course {i}" for i in range(1, count + 1)]
    return titles


def create_course(
    title: str,
    *,
    module_count: int = 3,
    difficulty: str = "Beginner",
    prerequisites: str = "",
    description: str | None = None,
    icon: str | None = None,
    company_id: int | None = None,
    price_cents: int = 0,
) -> Course:
    """Create a course with modules and quiz questions."""
    if not description:
        description = generate_course_overview(title)
    course = Course(
        title=title,
        description=description,
        difficulty=difficulty,
        prerequisites=prerequisites,
        icon=icon,
        company_id=company_id,
        price_cents=price_cents,
    )
    db.session.add(course)
    db.session.commit()

    for sec in generate_course_sections(title, module_count):
        section = CourseSection(
            course_id=course.id,
            title=sec["title"],
            content=sec["content"],
            order=sec["order"],
        )
        db.session.add(section)

    for q in generate_quiz_questions(title, 10):
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
    return course


def fetch_news_items() -> None:
    """Fetch latest news from the API and store new items."""
    news_api = get_setting("news_api_url") or DEFAULT_NEWS_API_URL
    resp = requests.get(news_api, timeout=10)
    resp.raise_for_status()
    for item in resp.json():
        title = item.get("title", {}).get("rendered", "")
        url = item.get("link", "")
        summary = item.get("excerpt", {}).get("rendered", "")
        if not NewsItem.query.filter_by(url=url).first():
            db.session.add(NewsItem(title=title, url=url, summary=summary))
    db.session.commit()
    # Keep only the 25 most recent items
    old_items = NewsItem.query.order_by(NewsItem.created_at.desc()).offset(25).all()
    for item in old_items:
        db.session.delete(item)
    if old_items:
        db.session.commit()
    set_setting("last_news_fetch", datetime.datetime.utcnow().isoformat())


def create_tables():
    """Create database tables if they don't exist."""
    db.create_all()
    # Ensure uploads folder exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    # Add icon column to Course if missing
    inspector = inspect(db.engine)
    cols = [c["name"] for c in inspector.get_columns("course")]
    if "icon" not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE course ADD COLUMN icon VARCHAR(200)"))
    if "company_id" not in cols:
        with db.engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE course ADD COLUMN company_id INTEGER REFERENCES company(id)")
            )
    if "price_cents" not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE course ADD COLUMN price_cents INTEGER DEFAULT 0"))
    user_cols = [c["name"] for c in inspector.get_columns("user")]
    if "is_company_admin" not in user_cols:
        with db.engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE user ADD COLUMN is_company_admin BOOLEAN DEFAULT 0")
            )
    # Initialize or update basic pages with richer default text
    default_pages = {
        "landing": (
            "Inicio",
            "¡Bienvenido a Monroy Asesores!\n\nSomos una firma mexicana especializada en consultoría de Recursos Humanos, coaching ejecutivo y diseño organizacional. Explora nuestros cursos y artículos para potenciar el talento de tu empresa."
        ),
        "about": (
            "Nosotros",
            "Monroy Asesores ayuda a las organizaciones a desarrollar estrategias efectivas de capital humano. Ofrecemos coaching ejecutivo, desarrollo de estructuras organizacionales y formación especializada en español."
        ),
        "contact": (
            "Contacto",
            "Nos encantaría escucharte. Escríbenos a [info@monroyasesores.com.mx](mailto:info@monroyasesores.com.mx) o utiliza el formulario a continuación."
        ),
        "faq": (
            "Preguntas Frecuentes",
            "### ¿Qué ofrece Monroy Asesores?\nProveemos consultoría y cursos de Recursos Humanos orientados a empresas mexicanas.\n\n### ¿Los cursos tienen costo?\nAlgunos cursos son gratuitos y otros requieren pago o asignación por parte de tu empresa."
        ),
        "terms": (
            "Términos y Aviso Legal",
            "## Términos\nTu información se utiliza únicamente para administrar el sitio y tus cursos.\n\n### Aviso Legal\nParte del contenido se genera con modelos de IA y puede contener errores."
        ),
    }
    for slug, (title, content) in default_pages.items():
        page = Page.query.filter_by(slug=slug).first()
        if page is None:
            db.session.add(Page(slug=slug, title=title, content=content))
    db.session.commit()
    if not get_setting("admin_email") and os.environ.get("ADMIN_EMAIL"):
        set_setting("admin_email", os.environ.get("ADMIN_EMAIL"))
    if not get_setting("site_topic"):
        set_setting("site_topic", "recursos humanos")
    if not get_setting("news_api_url"):
        set_setting("news_api_url", DEFAULT_NEWS_API_URL)
    if not get_setting("hostgator_host") and os.environ.get("HOSTGATOR_HOST"):
        set_setting("hostgator_host", os.environ.get("HOSTGATOR_HOST"))
    if not get_setting("hostgator_username") and os.environ.get("HOSTGATOR_USERNAME"):
        set_setting("hostgator_username", os.environ.get("HOSTGATOR_USERNAME"))
    if not get_setting("hostgator_password") and os.environ.get("HOSTGATOR_PASSWORD"):
        set_setting("hostgator_password", os.environ.get("HOSTGATOR_PASSWORD"))
    if not get_setting("hostgator_path") and os.environ.get("HOSTGATOR_REMOTE_PATH"):
        set_setting("hostgator_path", os.environ.get("HOSTGATOR_REMOTE_PATH"))


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
    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        if user and user.company_id:
            courses = Course.query.filter(
                (Course.company_id == None) | (Course.company_id == user.company_id)
            ).all()
        else:
            courses = Course.query.filter(Course.company_id == None).all()
    else:
        courses = Course.query.filter(Course.company_id == None).all()
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
    items = NewsItem.query.order_by(NewsItem.created_at.desc()).limit(25).all()
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


@app.route("/register/", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        company_name = request.form.get("company")
        if not User.query.filter_by(email=email).first():
            company = None
            if company_name:
                company = Company.query.filter_by(name=company_name).first()
                if not company:
                    company = Company(name=company_name)
                    db.session.add(company)
                    db.session.commit()
            user = User(
                email=email,
                password_hash=generate_password_hash(password),
                company=company,
            )
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            return redirect(url_for("index"))
        flash("Correo ya registrado", "danger")
    return render_template("register.html")


@app.route("/user_login/", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            return redirect(url_for("index"))
        flash("Credenciales inválidas", "danger")
    return render_template("user_login.html")


@app.route("/user_logout/")
def user_logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/company_admin/", methods=["GET", "POST"])
def company_admin():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("user_login"))
    user = User.query.get_or_404(user_id)
    if not user.is_company_admin:
        abort(403)
    if request.method == "POST":
        action = request.form.get("action")
        target_user_id = int(request.form.get("user_id"))
        course_id = int(request.form.get("course_id"))
        target_user = User.query.get_or_404(target_user_id)
        course = Course.query.get_or_404(course_id)
        if (
            target_user.company_id != user.company_id
            or course.company_id != user.company_id
        ):
            abort(403)
        if action == "assign":
            if not Enrollment.query.filter_by(
                user_id=target_user_id, course_id=course_id
            ).first():
                db.session.add(
                    Enrollment(
                        user_id=target_user_id, course_id=course_id, paid=True
                    )
                )
                db.session.commit()
                flash("Curso asignado", "success")
        elif action == "unassign":
            Enrollment.query.filter_by(
                user_id=target_user_id, course_id=course_id
            ).delete()
            db.session.commit()
            flash("Curso desasignado", "info")
        return redirect(url_for("company_admin"))
    company_users = User.query.filter_by(company_id=user.company_id).all()
    courses = Course.query.filter_by(company_id=user.company_id).all()
    enrollments = (
        Enrollment.query.join(User)
        .filter(User.company_id == user.company_id)
        .all()
    )
    return render_template(
        "company_admin.html", users=company_users, courses=courses, enrollments=enrollments
    )


@app.route("/courses/<int:course_id>/")
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    user_id = session.get("user_id")
    if not user_has_course_access(course, user_id):
        return render_template("course_paywall.html", course=course)
    sections = (
        CourseSection.query.filter_by(course_id=course_id)
        .order_by(CourseSection.order)
        .all()
    )
    if user_id:
        completed = [
            p.section_id
            for p in SectionProgress.query.filter_by(user_id=user_id, completed=True)
            .join(CourseSection)
            .filter(CourseSection.course_id == course_id)
            .all()
        ]
    else:
        completed = session.get("completed_sections", {}).get(str(course_id), [])
    all_done = bool(sections) and all(s.id in completed for s in sections)
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


@app.route("/courses/<int:course_id>/enroll/", methods=["POST"])
def enroll(course_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("user_login"))
    course = Course.query.get_or_404(course_id)
    if course.company_id is not None:
        abort(403)
    if course.price_cents <= 0:
        enrollment = Enrollment.query.filter_by(user_id=user_id, course_id=course.id).first()
        if not enrollment:
            enrollment = Enrollment(user_id=user_id, course_id=course.id, paid=True)
            db.session.add(enrollment)
            db.session.commit()
        return redirect(url_for("course_detail", course_id=course.id))
    checkout = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": course.title},
                    "unit_amount": course.price_cents,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=url_for(
            "enroll_success", course_id=course.id, _external=True
        ) + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=url_for("course_detail", course_id=course.id, _external=True),
    )
    return redirect(checkout.url)


@app.route("/courses/<int:course_id>/success/")
def enroll_success(course_id):
    session_id = request.args.get("session_id")
    if not session_id:
        abort(400)
    checkout = stripe.checkout.Session.retrieve(session_id)
    if checkout.payment_status == "paid":
        user_id = session.get("user_id")
        if not user_id:
            abort(400)
        enrollment = Enrollment.query.filter_by(
            user_id=user_id, course_id=course_id
        ).first()
        if not enrollment:
            enrollment = Enrollment(
                user_id=user_id, course_id=course_id, paid=True
            )
            db.session.add(enrollment)
        else:
            enrollment.paid = True
        db.session.commit()
        flash("Inscripción exitosa", "success")
        return redirect(url_for("course_detail", course_id=course_id))
    abort(400)


@app.route("/certificate/<int:course_id>/", methods=["GET", "POST"])
def certificate(course_id):
    course = Course.query.get_or_404(course_id)
    resp = require_course_access(course)
    if resp:
        return resp
    sections = (
        CourseSection.query.filter_by(course_id=course_id)
        .order_by(CourseSection.order)
        .all()
    )
    user_id = session.get("user_id")
    if user_id:
        completed = [
            p.section_id
            for p in SectionProgress.query.filter_by(user_id=user_id, completed=True)
            .join(CourseSection)
            .filter(CourseSection.course_id == course_id)
            .all()
        ]
    else:
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
    resp = require_course_access(course)
    if resp:
        return resp
    sections = (
        CourseSection.query.filter_by(course_id=course_id)
        .order_by(CourseSection.order)
        .all()
    )
    return render_template("course_full.html", course=course, sections=sections)


@app.route(
    "/courses/<int:course_id>/section/<int:section_id>/", methods=["GET", "POST"]
)
def course_section(course_id, section_id):
    course = Course.query.get_or_404(course_id)
    resp = require_course_access(course)
    if resp:
        return resp
    section = CourseSection.query.get_or_404(section_id)
    user_id = session.get("user_id")
    if user_id:
        completed = [
            p.section_id
            for p in SectionProgress.query.filter_by(user_id=user_id, completed=True)
            .join(CourseSection)
            .filter(CourseSection.course_id == course_id)
            .all()
        ]
    else:
        completed = session.get("completed_sections", {}).get(str(course_id), [])
    if request.method == "POST":
        correct = False
        if section.question and section.answer:
            answer = request.form.get("answer", "").strip().lower()
            if answer == section.answer.strip().lower():
                correct = True
        elif request.form.get("complete"):
            correct = True
        if not correct:
            return render_template(
                "course_section.html",
                course=course,
                section=section,
                completed=False,
                error=True,
            )
        if user_id:
            progress = SectionProgress.query.filter_by(
                user_id=user_id, section_id=section_id
            ).first()
            if not progress:
                progress = SectionProgress(
                    user_id=user_id, section_id=section_id, completed=True
                )
                db.session.add(progress)
            else:
                progress.completed = True
            db.session.commit()
        else:
            completed.append(section_id)
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
    resp = require_course_access(course)
    if resp:
        return resp
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
    resp = require_login()
    if resp:
        return resp
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
            topic = request.form.get("topic", "recursos humanos")
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
            company_name = request.form.get("company")
            company = None
            if company_name:
                company = Company.query.filter_by(name=company_name).first()
                if not company:
                    company = Company(name=company_name)
                    db.session.add(company)
                    db.session.commit()
            course = create_course(
                topic,
                module_count=module_count,
                difficulty=difficulty,
                prerequisites=prerequisites,
                description=description or None,
                icon=icon_name,
                company_id=company.id if company else None,
            )
            session.setdefault("completed_sections", {}).pop(str(course.id), None)
            session.setdefault("quiz_scores", {}).pop(str(course.id), None)
            session.setdefault("quiz_passed", {}).pop(str(course.id), None)
            SectionProgress.query.join(CourseSection).filter(
                CourseSection.course_id == course.id
            ).delete(synchronize_session=False)
            db.session.commit()
            session.modified = True
        elif action == "update_course":
            course = Course.query.get_or_404(request.form.get("id"))
            course.title = request.form.get("title")
            course.description = request.form.get("description")
            course.difficulty = request.form.get("difficulty")
            course.prerequisites = request.form.get("prerequisites")
            if request.form.get("remove_icon"):
                if course.icon:
                    try:
                        os.remove(
                            os.path.join(app.config["UPLOAD_FOLDER"], course.icon)
                        )
                    except Exception:
                        pass
                course.icon = None
            file = request.files.get("icon")
            if file and file.filename:
                os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                if course.icon:
                    try:
                        os.remove(
                            os.path.join(app.config["UPLOAD_FOLDER"], course.icon)
                        )
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
        elif action == "generate_questions":
            course = Course.query.get_or_404(request.form.get("id"))
            QuizQuestion.query.filter_by(course_id=course.id).delete()
            for q in generate_quiz_questions(course.title, 10):
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
        elif action == "clear_ai_content":
            BlogPost.query.delete()
            NewsItem.query.delete()
            for course in Course.query.all():
                db.session.delete(course)
            db.session.commit()
            # Remove any stored progress when wiping generated content
            SectionProgress.query.delete()
            db.session.commit()
            session.pop("completed_sections", None)
            session.pop("quiz_scores", None)
            session.pop("quiz_passed", None)
            session.modified = True
        elif action == "update_settings":
            set_setting("site_topic", request.form.get("site_topic", "").strip())
            set_setting("news_api_url", request.form.get("news_api_url", "").strip())
        elif action == "update_ftp":
            set_setting("hostgator_host", request.form.get("hostgator_host", "").strip())
            set_setting("hostgator_username", request.form.get("hostgator_username", "").strip())
            set_setting("hostgator_password", request.form.get("hostgator_password", "").strip())
            set_setting("hostgator_path", request.form.get("hostgator_path", "").strip())
        elif action == "upload_image":
            slug = secure_filename(request.form.get("slug", ""))
            allowed = [p.slug for p in Page.query.all()] + ["hero"]
            if slug in allowed:
                file = request.files.get("image")
                if file and file.filename:
                    os.makedirs("static", exist_ok=True)
                    path = os.path.join("static", f"{slug}.jpg")
                    file.save(path)
        elif action == "delete_image":
            slug = secure_filename(request.form.get("slug", ""))
            allowed = [p.slug for p in Page.query.all()] + ["hero"]
            if slug in allowed:
                path = os.path.join("static", f"{slug}.jpg")
                if os.path.exists(path):
                    os.remove(path)
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
    last_fetch = get_setting("last_news_fetch")
    site_topic = get_setting("site_topic", "recursos humanos")
    news_api_url = get_setting("news_api_url", DEFAULT_NEWS_API_URL)
    hostgator_host = get_setting("hostgator_host", "")
    hostgator_username = get_setting("hostgator_username", "")
    hostgator_password = get_setting("hostgator_password", "")
    hostgator_path = get_setting("hostgator_path", "/public_html")
    return render_template(
        "admin.html",
        pages=pages,
        posts=posts,
        courses=courses,
        items=items,
        last_news_fetch=last_fetch,
        site_topic=site_topic,
        news_api_url=news_api_url,
        hostgator_host=hostgator_host,
        hostgator_username=hostgator_username,
        hostgator_password=hostgator_password,
        hostgator_path=hostgator_path,
    )


@app.route("/admin/deploy_hostgator", methods=["POST"])
def deploy_hostgator_route():
    require_login()
    """Generate the static site and upload it to HostGator via FTP."""
    env = os.environ.copy()
    env.update({
        "HOSTGATOR_HOST": get_setting("hostgator_host", ""),
        "HOSTGATOR_USERNAME": get_setting("hostgator_username", ""),
        "HOSTGATOR_PASSWORD": get_setting("hostgator_password", ""),
        "HOSTGATOR_REMOTE_PATH": get_setting("hostgator_path", "/public_html"),
    })
    try:
        result = subprocess.run(
            [sys.executable, "deploy_hostgator.py"],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        flash("Sitio desplegado a HostGator.", "success")
        if result.stdout:
            flash(result.stdout, "info")
        if result.stderr:
            flash(result.stderr, "warning")
    except subprocess.CalledProcessError as e:
        output = (e.stdout or "") + (e.stderr or "")
        flash(f"El despliegue falló: {output}", "danger")
    return redirect(url_for("admin"))


@app.route("/admin/delete_hostgator", methods=["POST"])
def delete_hostgator_route():
    require_login()
    """Remove the static site from HostGator via FTP."""
    env = os.environ.copy()
    env.update({
        "HOSTGATOR_HOST": get_setting("hostgator_host", ""),
        "HOSTGATOR_USERNAME": get_setting("hostgator_username", ""),
        "HOSTGATOR_PASSWORD": get_setting("hostgator_password", ""),
        "HOSTGATOR_REMOTE_PATH": get_setting("hostgator_path", "/public_html"),
    })
    try:
        result = subprocess.run(
            [sys.executable, "delete_hostgator.py"],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        flash("Archivos remotos eliminados de HostGator.", "success")
        if result.stdout:
            flash(result.stdout, "info")
        if result.stderr:
            flash(result.stderr, "warning")
    except subprocess.CalledProcessError as e:
        output = (e.stdout or "") + (e.stderr or "")
        flash(f"La eliminación falló: {output}", "danger")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    with app.app_context():
        create_tables()
    app.run(debug=True)
