from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.models.models import PanTransferSyncTask, ensure_runtime_storage_tables, engine
from app.services.pan_transfer.follow_tasks import reconcile_follow_task_progress_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair follow-task progress from materialized update state")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--task-id", type=int, help="Repair one follow task")
    scope.add_argument("--all", action="store_true", help="Repair every follow task")
    args = parser.parse_args()

    ensure_runtime_storage_tables()
    with Session(engine) as session:
        query = session.query(PanTransferSyncTask).order_by(PanTransferSyncTask.id.asc())
        if args.task_id is not None:
            query = query.filter(PanTransferSyncTask.id == int(args.task_id))
        tasks = query.all()
        if args.task_id is not None and not tasks:
            raise SystemExit(f"follow task not found: {args.task_id}")

        repaired_count = 0
        for task in tasks:
            state, changed = reconcile_follow_task_progress_state(
                task,
                updated_by="progress-repair",
            )
            if not changed:
                continue
            session.add(task)
            session.flush()
            repaired_count += 1
            print(
                f"repaired follow task #{int(task.id)}: "
                f"episode={state.get('episode') or '-'}"
            )

        session.commit()
        print(f"follow progress repair complete: scanned={len(tasks)} repaired={repaired_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
