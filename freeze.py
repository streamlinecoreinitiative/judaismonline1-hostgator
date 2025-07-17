from app import app, Course, create_tables
from flask_frozen import Freezer

import re

app.config['FREEZER_DESTINATION'] = 'docs'
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

if __name__ == '__main__':
    with app.app_context():
        create_tables()
    freezer.freeze()
