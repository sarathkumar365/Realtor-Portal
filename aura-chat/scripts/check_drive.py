"""Check the service account can write to the Shared Drive's Test folder.

Not a pytest: it calls Google. Reads the key and folder ids from .env, never
prints the key. Creates "check_drive/<timestamp>" under the Test folder and
uploads a one-page PDF into it; delete that folder by hand afterwards.

    .venv/bin/python scripts/check_drive.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf

from app.capabilities.unbrander.adapters.drive_google import GoogleDriveWriter
from app.capabilities.unbrander.ports import DriveWriteFailed
from app.config import load


async def main() -> int:
    config = load()
    missing = [name for name, value in (
        ("GOOGLE_SERVICE_ACCOUNT_JSON", config.google_service_account_json),
        ("DRIVE_SHARED_DRIVE_ID", config.drive_shared_drive_id),
        ("DRIVE_TEST_ROOT_FOLDER_ID", config.drive_test_root_folder_id)) if not value]
    if missing:
        print("not set in .env: " + ", ".join(missing))
        return 2

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "check_drive")
    pdf = doc.tobytes()

    drive = GoogleDriveWriter(config.google_service_account_json, config.drive_shared_drive_id)
    try:
        checks, existed = await drive.find_or_create_folder(
            config.drive_test_root_folder_id, "check_drive")
        print(f"  ok    check_drive folder {'found' if existed else 'created'}")
        name = time.strftime("%Y-%m-%d %H.%M.%S")
        run, _ = await drive.find_or_create_folder(checks, name)
        print("  ok    run folder created")
        found, existed = await drive.find_or_create_folder(checks, name)
        if (found, existed) != (run, True):
            print("  FAIL  the run folder was not found again by name")
            return 1
        print("  ok    run folder found again by name")
        file_id = await drive.upload_pdf(run, "check_drive.pdf", pdf)
        print(f"  ok    uploaded a PDF (file id {file_id})")
    except DriveWriteFailed as error:
        print(f"  FAIL  {error}")
        return 1
    finally:
        await drive.aclose()
    print("\nPASS: the Test folder now holds check_drive/<time>/check_drive.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
