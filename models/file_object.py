
from datetime import datetime, timezone

from extensions import db


class FileObject(db.Model):
    __tablename__ = "file_objects"

    id = db.Column(db.Integer, primary_key=True)

    storage_key = db.Column(
        db.String(64),
        nullable=False,
        unique=True,
        index=True
    )

    filename = db.Column(
        db.String(255),
        nullable=False
    )

    content_type = db.Column(
        db.String(150),
        nullable=False
    )

    size_bytes = db.Column(
        db.BigInteger,
        nullable=False
    )

    data = db.Column(
        db.LargeBinary,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<FileObject {self.storage_key}>"
