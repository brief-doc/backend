from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import History

KST = timezone(timedelta(hours=9))


def record(db: Session, user_id: int, change_table: str, change_text: str) -> None:
    db.add(
        History(
            user_id=user_id,
            change_table=change_table,
            change_text=change_text,
            change_time=datetime.now(KST),
        )
    )
