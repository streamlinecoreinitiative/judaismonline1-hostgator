from app import app, Course, CourseSection, QuizQuestion, create_tables
from flask_frozen import Freezer

import re
import os
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

@freezer.register_generator
def certificate():
    for course in Course.query.all():
        yield {'course_id': course.id}


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
