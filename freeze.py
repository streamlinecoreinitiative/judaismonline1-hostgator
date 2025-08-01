import os
import subprocess
import sys

# Ensure required packages are available. This helps when the freeze command
# is triggered from environments that may not have the project's dependencies
# installed (for example when called from the admin deployment page).
try:
    from flask import Flask  # noqa: F401 - check only for import
    from flask_sqlalchemy import SQLAlchemy  # noqa: F401
    from flask_frozen import Freezer
except ImportError:
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)
    from flask_frozen import Freezer

from app import app, Course, CourseSection, QuizQuestion, create_tables

import re
import shutil

app.config['FREEZER_DESTINATION'] = 'docs'
app.config['GENERATING_STATIC'] = True
app.config['SHOW_LOGIN'] = False
app.config['FREEZER_IGNORE_URLS'] = [
    re.compile(r'/admin'),
    re.compile(r'/login'),
    re.compile(r'/logout'),
]
# Use relative URLs so the site works when hosted from a subdirectory
app.config['FREEZER_RELATIVE_URLS'] = True
freezer = Freezer(app)

@freezer.register_generator
def course_detail():
    for course in Course.query.all():
        yield {'course_id': course.id}


# Certificate pages are only available for users who have completed a
# course, so they rely on session state and cannot be generated
# statically.  The corresponding generator previously attempted to
# freeze ``/certificate/<course_id>/`` pages which resulted in a
# ``403 FORBIDDEN`` error during the freeze process.  Removing this
# generator avoids the error and mirrors the behaviour of the site,
# where certificates are generated dynamically at runtime.


@freezer.register_generator
def course_full():
    for course in Course.query.all():
        yield {'course_id': course.id}


@freezer.register_generator
def course_section():
    for section in CourseSection.query.all():
        yield {'course_id': section.course_id, 'section_id': section.id}


@freezer.register_generator
def course_quiz():
    for course in Course.query.all():
        yield {'course_id': course.id}

if __name__ == '__main__':
    with app.app_context():
        create_tables()
    freezer.freeze()
    for path in ['admin', 'login', 'logout']:
        full = os.path.join(app.config['FREEZER_DESTINATION'], path)
        if os.path.isdir(full):
            shutil.rmtree(full)
