from app import app, Course
from flask_frozen import Freezer

app.config['FREEZER_DESTINATION'] = 'docs'
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
    freezer.freeze()
