from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import UploadFile

from app.repositories import student_report_repository, student_repository
from app.services.audit_service import write_audit_log
from app.services.private_storage import ensure_private_storage, private_disk_path, report_relative_path


MAX_REPORT_FILE_SIZE = 20 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 2_000
REPORT_TYPES = {"weekly", "monthly", "project_progress", "research", "demo", "other"}
ALLOWED_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalized_text(value: str | None, field_name: str, min_length: int = 0, max_length: int = 5_000) -> str | None:
    value = (value or "").strip()
    if not value:
        if min_length:
            raise ValueError(f"{field_name} khong duoc de trong.")
        return None
    if len(value) < min_length or len(value) > max_length:
        raise ValueError(f"{field_name} phai co tu {min_length} den {max_length} ky tu.")
    return value


def _validated_link(value: str | None) -> str | None:
    value = _normalized_text(value, "Link tham khao", max_length=2_000)
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Neu khong co link GitHub/Drive, hay de trong o nay. Neu co, link phai bat dau bang http:// hoac https://.")
    return value


def _safe_original_filename(filename: str | None) -> str:
    cleaned = Path(filename or "").name.replace("\x00", "").strip()
    cleaned = "".join(char for char in cleaned if char.isprintable())
    cleaned = cleaned.replace('"', "").replace("'", "")
    if not cleaned:
        raise ValueError("Ten file khong hop le.")
    if len(cleaned) > 180:
        suffix = Path(cleaned).suffix
        cleaned = f"{Path(cleaned).stem[:160]}{suffix[:12]}"
    return cleaned


def _validate_file_signature(suffix: str, content: bytes) -> None:
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("File PDF khong hop le.")
    if suffix == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("File PNG khong hop le.")
    if suffix in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise ValueError("File JPG khong hop le.")
    if suffix in {".doc", ".ppt"} and not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValueError("File Office khong hop le.")
    if suffix in {".docx", ".pptx", ".xlsx", ".zip"} and not content.startswith(b"PK\x03\x04"):
        raise ValueError("File nen hoac Office khong hop le.")
    if suffix in {".docx", ".pptx", ".xlsx", ".zip"}:
        try:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                total_size = sum(entry.file_size for entry in entries)
        except BadZipFile as exc:
            raise ValueError("File nen hoac Office khong hop le.") from exc
        if len(entries) > MAX_ARCHIVE_FILES or total_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
            raise ValueError("File nen vuot qua gioi han an toan.")


async def _save_upload(upload: UploadFile | None, report_id: int, version_no: int):
    if not upload or not upload.filename:
        return None, None, None, None
    original_filename = _safe_original_filename(upload.filename)
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_FILE_TYPES:
        raise ValueError("Dinh dang file chua duoc phep. Chi nhan PDF, Office, ZIP hoac anh PNG/JPG.")
    content = await upload.read(MAX_REPORT_FILE_SIZE + 1)
    if not content:
        raise ValueError("File dinh kem dang rong.")
    if len(content) > MAX_REPORT_FILE_SIZE:
        raise ValueError("File dinh kem vuot qua gioi han 20 MB.")
    _validate_file_signature(suffix, content)

    stored_filename = f"{uuid4().hex}{suffix}"
    relative_path = report_relative_path(report_id, version_no, stored_filename)
    target = private_disk_path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return original_filename, relative_path, len(content), ALLOWED_FILE_TYPES[suffix]


def _has_attachment(upload: UploadFile | None) -> bool:
    return bool(upload and (upload.filename or "").strip())


def _report_label(report) -> str:
    return f"{report['student_code']} - {report['title']}"


def _reviewer_id(db, requested_reviewer_id: int | None) -> int:
    reviewers = student_report_repository.list_active_lab_managers(db)
    reviewer_ids = {row["id"] for row in reviewers}
    if requested_reviewer_id is not None:
        if requested_reviewer_id not in reviewer_ids:
            raise ValueError("Giao vien nhan bao cao khong hop le hoac da bi khoa.")
        return requested_reviewer_id
    if len(reviewers) == 1:
        return reviewers[0]["id"]
    if not reviewers:
        raise ValueError("He thong chua co tai khoan lab manager dang hoat dong.")
    raise ValueError("Vui long chon giao vien nhan bao cao.")


def _validate_submission(title: str | None, report_type: str | None, description: str | None, external_link: str | None,
                         require_metadata: bool):
    normalized_title = _normalized_text(title, "Tieu de bao cao", 3, 180) if require_metadata else None
    normalized_type = (report_type or "").strip()
    if require_metadata and normalized_type not in REPORT_TYPES:
        raise ValueError("Loai bao cao khong hop le.")
    return normalized_title, normalized_type, _normalized_text(description, "Mo ta", max_length=5_000), _validated_link(external_link)


async def create_report(db, actor: dict, title: str, report_type: str, description: str | None,
                        external_link: str | None, reviewer_id: int | None, attachment: UploadFile | None, request=None) -> dict:
    title, report_type, description, external_link = _validate_submission(title, report_type, description, external_link, True)
    student_id = actor.get("student_id")
    student = student_repository.get_student_by_id(db, student_id) if student_id else None
    if not student or student["status"] != "active":
        raise ValueError("Ho so sinh vien khong con hoat dong.")
    if not _has_attachment(attachment) and not external_link:
        raise ValueError("Can dinh kem it nhat mot file hoac link tham khao.")

    storage_path = None
    try:
        db.execute("BEGIN IMMEDIATE")
        target_reviewer_id = _reviewer_id(db, reviewer_id)
        now_text = _now_text()
        report_id = student_report_repository.create_report(db, student_id, target_reviewer_id, title, report_type, now_text)
        ensure_private_storage()
        original_filename, storage_path, file_size, media_type = await _save_upload(attachment, report_id, 1)
        student_report_repository.create_version(
            db, report_id, 1, description, external_link, original_filename, storage_path, file_size, media_type, actor["id"], now_text
        )
        report = student_report_repository.get_report(db, report_id)
        write_audit_log(
            db, actor, "student_reports.submit", "student_report", report_id, _report_label(report),
            {"report_type": report_type, "reviewer_id": target_reviewer_id, "version_no": 1, "has_attachment": bool(storage_path)}, request,
        )
        return report_detail(db, report_id)
    except Exception:
        if storage_path:
            path = private_disk_path(storage_path)
            if path.exists():
                path.unlink()
        raise


async def resubmit_report(db, actor: dict, report_id: int, description: str | None, external_link: str | None,
                          attachment: UploadFile | None, request=None) -> dict:
    _, _, description, external_link = _validate_submission(None, None, description, external_link, False)
    report = student_report_repository.get_report_for_student(db, report_id, actor.get("student_id"))
    if not report:
        raise LookupError("Khong tim thay bao cao.")
    if report["status"] != "revision_requested":
        raise ValueError("Chi co the nop lai bao cao dang duoc yeu cau chinh sua.")
    if not _has_attachment(attachment) and not external_link:
        raise ValueError("Can dinh kem file moi hoac link tham khao cho lan nop lai.")

    storage_path = None
    try:
        db.execute("BEGIN IMMEDIATE")
        next_version = int(report["current_version"]) + 1
        now_text = _now_text()
        ensure_private_storage()
        original_filename, storage_path, file_size, media_type = await _save_upload(attachment, report_id, next_version)
        if not student_report_repository.update_for_resubmission(db, report_id, next_version, now_text):
            raise ValueError("Bao cao khong con o trang thai can chinh sua.")
        student_report_repository.create_version(
            db, report_id, next_version, description, external_link, original_filename, storage_path, file_size, media_type, actor["id"], now_text
        )
        updated = student_report_repository.get_report(db, report_id)
        write_audit_log(
            db, actor, "student_reports.resubmit", "student_report", report_id, _report_label(updated),
            {"version_no": next_version, "has_attachment": bool(storage_path)}, request,
        )
        return report_detail(db, report_id)
    except Exception:
        if storage_path:
            path = private_disk_path(storage_path)
            if path.exists():
                path.unlink()
        raise


def report_detail(db, report_id: int) -> dict:
    report = student_report_repository.get_report(db, report_id)
    if not report:
        raise LookupError("Khong tim thay bao cao.")
    result = dict(report)
    result["versions"] = [dict(row) for row in student_report_repository.list_versions(db, report_id)]
    result["feedbacks"] = [dict(row) for row in student_report_repository.list_feedbacks(db, report_id)]
    return result


def get_student_report_detail(db, actor: dict, report_id: int) -> dict:
    report = student_report_repository.get_report_for_student(db, report_id, actor.get("student_id"))
    if not report:
        raise PermissionError("Ban khong co quyen xem bao cao nay.")
    return report_detail(db, report_id)


def get_staff_report_detail(db, actor: dict, report_id: int) -> dict:
    report = student_report_repository.get_report(db, report_id)
    if not report:
        raise LookupError("Khong tim thay bao cao.")
    if actor.get("role") != "admin" and report["reviewer_id"] != actor.get("id"):
        raise PermissionError("Bao cao nay khong duoc gui cho ban.")
    if actor.get("role") == "lab_manager":
        student_report_repository.mark_current_version_viewed(db, report_id, _now_text())
    return report_detail(db, report_id)


def get_version_for_student(db, actor: dict, report_id: int, version_no: int):
    report = student_report_repository.get_report_for_student(db, report_id, actor.get("student_id"))
    if not report:
        raise PermissionError("Ban khong co quyen tai file nay.")
    version = student_report_repository.get_version(db, report_id, version_no)
    if not version or not version["storage_path"]:
        raise LookupError("Khong tim thay file dinh kem.")
    return report, version


def get_version_for_staff(db, actor: dict, report_id: int, version_no: int):
    report = student_report_repository.get_report(db, report_id)
    if not report:
        raise LookupError("Khong tim thay bao cao.")
    if actor.get("role") != "admin" and report["reviewer_id"] != actor.get("id"):
        raise PermissionError("Bao cao nay khong duoc gui cho ban.")
    version = student_report_repository.get_version(db, report_id, version_no)
    if not version or not version["storage_path"]:
        raise LookupError("Khong tim thay file dinh kem.")
    return report, version


def review_report(db, actor: dict, report_id: int, payload, request=None) -> dict:
    payload.validate_review()
    report = student_report_repository.get_report(db, report_id)
    if not report:
        raise LookupError("Khong tim thay bao cao.")
    if actor.get("role") != "admin" and report["reviewer_id"] != actor.get("id"):
        raise PermissionError("Bao cao nay khong duoc gui cho ban.")
    if report["status"] != "submitted":
        raise ValueError("Chi co the phan hoi phien ban dang cho xem.")

    db.execute("BEGIN IMMEDIATE")
    now_text = _now_text()
    if not student_report_repository.update_review_status(db, report_id, payload.status, now_text):
        raise ValueError("Bao cao da duoc xu ly boi mot phien khac.")
    student_report_repository.create_feedback(
        db, report_id, report["current_version_id"], actor["id"], payload.status, payload.comment, now_text
    )
    action_prefix = "student_reports.admin_override" if actor.get("role") == "admin" else "student_reports.review"
    write_audit_log(
        db, actor, action_prefix, "student_report", report_id, _report_label(report),
        {"status": payload.status, "version_no": report["current_version"], "has_comment": bool(payload.comment)}, request,
    )
    return report_detail(db, report_id)
