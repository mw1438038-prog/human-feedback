
import uuid

from werkzeug.utils import secure_filename

from extensions import db
from models.file_object import FileObject


def save_file(content, filename, content_type):
    """
    Store file bytes in Neon PostgreSQL.
    Does not commit the transaction.
    """

    if not isinstance(content, bytes):
        raise TypeError("File content must be bytes.")

    if not content:
        raise ValueError("Cannot store an empty file.")

    safe_filename = secure_filename(filename or "")

    if not safe_filename:
        safe_filename = "uploaded-file"

    storage_key = uuid.uuid4().hex

    file_object = FileObject(
        storage_key=storage_key,
        filename=safe_filename,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(content),
        data=content
    )

    db.session.add(file_object)
    db.session.flush()

    return storage_key


def get_file(storage_key):
    """Retrieve a stored file by its storage key."""

    if not storage_key:
        return None

    return FileObject.query.filter_by(
        storage_key=storage_key
    ).first()


def delete_file(storage_key):
    """Delete a stored file inside the current transaction."""

    file_object = get_file(storage_key)

    if file_object:
        db.session.delete(file_object)
        db.session.flush()

    return bool(file_object)
