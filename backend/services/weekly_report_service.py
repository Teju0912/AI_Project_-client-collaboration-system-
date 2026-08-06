from models import Task, Project


def generate_report(db, project_id):
    project = db.query(Project).filter(Project.id == project_id).first()
    project_name = project.name if project else str(project_id)

    tasks = db.query(Task).filter(Task.project_id == project_id).all()

    total = len(tasks)
    completed = len([t for t in tasks if t.status == "done"])
    in_progress = len([t for t in tasks if t.status == "in_progress"])
    testing = len([t for t in tasks if t.status == "testing"])
    todo = len([t for t in tasks if t.status == "todo"])

    completion_pct = round(100 * completed / total) if total > 0 else 0

    if completion_pct >= 80:
        summary = (
            f"The project is progressing excellently with {completion_pct}% completion. "
            f"Most tasks have been finished and the project is on track."
        )
    elif completion_pct >= 50:
        summary = (
            f"The project is progressing well with {completion_pct}% completion. "
            f"Most tasks have been completed and remaining work is currently in progress."
        )
    elif completion_pct >= 20:
        summary = (
            f"The project is in early-to-mid execution with {completion_pct}% completion. "
            f"Several tasks are underway and work is progressing steadily."
        )
    else:
        summary = (
            f"The project is in its early stages with {completion_pct}% completion. "
            f"Work has begun and tasks are being picked up by the team."
        )

    report = f"""Project: {project_name}

Total Tasks: {total}
Completed: {completed}
In Progress: {in_progress}
Testing: {testing}
Pending (To Do): {todo}

Completion: {completion_pct}%

Summary:
{summary}
"""

    return report
