"""Google-Drive-Sync von CompletionistMD: neue Ordner und Dateien, doppelte
Ordner in Drive, nur ein Abgleich zur Zeit."""

from __future__ import annotations

import hashlib
import itertools
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.drive import FOLDER_MIME, NotFound  # noqa: E402
from mdeditor.gdrive import HashCache, SyncLock, SyncWorker, remote_tree, run_sync  # noqa: E402

TOP = "Completionist Vault"


class FakeDrive:
    """Drive mit drive.file-Sicht: nur eigene Eintraege, Liste in beliebiger Reihenfolge."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.ids = itertools.count(1)
        self.reverse = False

    def _new_id(self, prefix: str) -> tuple[str, str]:
        n = next(self.ids)
        return f"{prefix}{n}", f"2026-10-01T00:00:{n:02d}Z"

    def list_all(self):
        items = [dict(v) for v in self.items.values()]
        return items[::-1] if self.reverse else items

    def exists(self, fid):
        return fid in self.items

    def create_folder(self, name, parent):
        fid, created = self._new_id("f")
        self.items[fid] = {"id": fid, "name": name, "mimeType": FOLDER_MIME, "createdTime": created,
                           "parents": [parent] if parent else ["ROOT"]}
        return fid

    def upload(self, path, name, parent, file_id):
        if parent not in self.items:
            raise NotFound("parent")
        if file_id:
            entry = self.items[file_id]
        else:
            fid, created = self._new_id("d")
            entry = self.items[fid] = {"id": fid, "name": name, "mimeType": "text/plain",
                                       "createdTime": created, "parents": [parent]}
        entry["md5Checksum"] = hashlib.md5(path.read_bytes()).hexdigest()
        entry["modifiedTime"] = "2026-01-01T00:00:00Z"
        return entry

    def parent_of(self, name: str) -> list[str]:
        return [v["parents"][0] for v in self.items.values() if v["name"] == name]


def test_new_nested_folders_and_files_are_uploaded(tmp_path):
    (tmp_path / "a.md").write_text("a")
    drive, hashes = FakeDrive(), HashCache(None)
    run_sync(drive, tmp_path, TOP, hashes)
    (tmp_path / "Neu" / "Tief").mkdir(parents=True)
    (tmp_path / "Neu" / "Tief" / "b.md").write_text("b")
    (tmp_path / "Neu" / "Plan.xlsx").write_bytes(b"x")
    result = run_sync(drive, tmp_path, TOP, hashes)
    assert result["new"] == 2
    assert result["folder_id"] == remote_tree(drive, TOP).top_id
    tree = remote_tree(drive, TOP)
    assert {"a.md", "Neu/Plan.xlsx", "Neu/Tief/b.md"} == set(tree.files)


def test_duplicate_folders_new_files_always_go_to_the_oldest(tmp_path):
    # Zwei Fenster legten "Guides" gleichzeitig an (vor MD 1.9.1 moeglich)
    (tmp_path / "Guides").mkdir()
    (tmp_path / "Guides" / "a.md").write_text("a")
    drive, hashes = FakeDrive(), HashCache(None)
    top = drive.create_folder(TOP, None)
    oldest = drive.create_folder("Guides", top)
    younger = drive.create_folder("Guides", top)
    (tmp_path / "Guides" / "b.md").write_text("b")
    drive.upload(tmp_path / "Guides" / "b.md", "b.md", younger, None)  # liegt im juengeren

    run_sync(drive, tmp_path, TOP, hashes)
    drive.reverse = True  # Google liefert die Liste diesmal andersherum
    (tmp_path / "Guides" / "neu.md").write_text("n")
    result = run_sync(drive, tmp_path, TOP, hashes)

    assert result["uploaded"] == 1
    assert drive.parent_of("a.md") == [oldest]
    assert drive.parent_of("neu.md") == [oldest]
    assert drive.parent_of("b.md") == [younger]  # erkannt, nicht noch einmal hochgeladen


def test_duplicate_top_folders_are_merged(tmp_path):
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")
    drive, hashes = FakeDrive(), HashCache(None)
    first = drive.create_folder(TOP, None)
    second = drive.create_folder(TOP, None)
    drive.upload(tmp_path / "b.md", "b.md", second, None)
    drive.reverse = True
    run_sync(drive, tmp_path, TOP, hashes)
    assert drive.parent_of("a.md") == [first]
    assert drive.parent_of("b.md") == [second]


def test_only_one_sync_at_a_time(tmp_path):
    first, second = SyncLock(tmp_path / "gdrive.lock"), SyncLock(tmp_path / "gdrive.lock")
    assert first.acquire()
    assert not second.acquire()  # zweites Fenster wartet
    first.release()
    assert second.acquire()
    second.release()


def test_worker_reports_busy_while_another_window_syncs(tmp_path):
    class Store:
        folder = tmp_path / "credentials"

        def credentials(self):
            raise AssertionError("darf nicht abgleichen")

    held = SyncLock(tmp_path / "gdrive.lock")
    assert held.acquire()
    worker = SyncWorker(Store())
    seen = []
    worker.failed.connect(lambda kind, msg: seen.append(kind))
    worker.sync(str(tmp_path), TOP)
    held.release()
    assert seen == ["busy"]


def test_log_records_each_run_and_keeps_the_tail(tmp_path, monkeypatch):
    from mdeditor.gdrive import SyncLog

    monkeypatch.setattr(SyncLog, "KEEP", 3)
    log = SyncLog(tmp_path / "gdrive.log")
    for n in range(5):
        log.write(f"Zeile {n}")
    lines = (tmp_path / "gdrive.log").read_text(encoding="utf-8").splitlines()
    assert [ln.split("  ", 1)[1] for ln in lines] == ["Zeile 2", "Zeile 3", "Zeile 4"]


def test_busy_run_is_logged(tmp_path):
    class Store:
        folder = tmp_path / "credentials"

    held = SyncLock(tmp_path / "gdrive.lock")
    assert held.acquire()
    SyncWorker(Store()).sync(str(tmp_path), TOP)
    held.release()
    assert "anderes Fenster" in (tmp_path / "gdrive.log").read_text(encoding="utf-8")


def test_skipped_files_turn_the_status_yellow(tmp_path):
    from PySide6.QtWidgets import QApplication

    from mdeditor.gdrive import GDriveSync

    # volle QApplication: spaetere Tests im selben Lauf brauchen Fenster
    QApplication.instance() or QApplication(["pytest"])

    class Store:
        folder = tmp_path / "credentials"

        def has_token(self):
            return True

    sync = GDriveSync(store=Store())
    seen = []
    sync.statusChanged.connect(lambda state, text, tip: seen.append((state, text, tip)))
    try:
        result = {"checked": 3, "uploaded": 1, "new": 1, "conflicts": 0, "time": 0,
                  "folder_id": "abc", "failed": {"Guide/Plan.docx": "Drive-Fehler 403: Speicher voll"}}
        sync.running = True
        sync._on_finished(result)
        state, text, tip = seen[-1]
        assert state == "warn" and "1 übersprungen" in text
        assert "drive/folders/abc" in tip and "Speicher voll" in tip and "gdrive.log" in tip
        sync._on_finished(dict(result, failed={}))
        assert seen[-1][0] == "ok"
    finally:
        sync.shutdown()


def test_token_is_only_rewritten_when_it_changed(tmp_path):
    import json

    from core.drive import TokenStore

    store = TokenStore(tmp_path)
    store.save_info(json.dumps({"token": "a", "refresh_token": "r"}))
    token_file = tmp_path / TokenStore.TOKEN_FILE
    stamp = token_file.stat().st_mtime_ns
    store.save_info(json.dumps({"refresh_token": "r", "token": "a"}))  # gleich, andere Reihenfolge
    assert token_file.stat().st_mtime_ns == stamp
    store.save_info(json.dumps({"token": "b", "refresh_token": "r"}))
    assert store.load_info()["token"] == "b"
    assert not list(tmp_path.glob("*.tmp"))
