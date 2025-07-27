"""Batch course creation script."""
import argparse
from app import app, create_tables, generate_course_topics, create_course


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate multiple courses using the local AI model"
    )
    parser.add_argument("topic", help="General subject for suggested courses")
    parser.add_argument("--courses", type=int, default=3, help="Number of courses to create")
    parser.add_argument("--modules", type=int, default=3, help="Number of modules per course")
    parser.add_argument("--difficulty", default="Beginner", help="Difficulty level for all courses")
    parser.add_argument("--prerequisites", default="", help="Prerequisites text for all courses")
    args = parser.parse_args()

    with app.app_context():
        create_tables()
        titles = generate_course_topics(args.topic, args.courses)
        for title in titles:
            course = create_course(
                title,
                module_count=args.modules,
                difficulty=args.difficulty,
                prerequisites=args.prerequisites,
            )
            print(f"Created course '{course.title}' (id {course.id})")


if __name__ == "__main__":
    main()
