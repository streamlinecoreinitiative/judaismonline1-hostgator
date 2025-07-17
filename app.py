import datetime
import os

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import ollama

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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


def generate_text(prompt: str) -> str:
    """Generate text from the local Llama 3 model via ollama."""
    stream = ollama.chat(
        model="llama3:8b",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    return "".join(chunk["message"]["content"] for chunk in stream)


@app.before_first_request
def create_tables():
    db.create_all()


@app.route("/")
def index():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template("index.html", posts=posts)


@app.route("/courses")
def courses():
    courses = Course.query.all()
    return render_template("courses.html", courses=courses)


@app.route("/courses/<int:course_id>")
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template("course_detail.html", course=course)


@app.route("/certificate/<int:course_id>")
def certificate(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template("certificate.html", course=course)


@app.route("/admin", methods=["GET", "POST"])
def admin():
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
        return redirect(url_for("admin"))
    return render_template("admin.html")


if __name__ == "__main__":
    app.run(debug=True)
