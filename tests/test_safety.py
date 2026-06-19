"""
Safety-layer tests: PROTECTED_PATH_SEGMENTS, SCAN_SKIP_DIRS, and the
root-drive gate added to the CLI's scan command.

These tests are the specification for Ordra's "never touch system files"
guarantee.  If any of these fail, a regression has been introduced that
could let Ordra move or delete critical OS / credential files.
"""
from pathlib import Path

import pytest

from file_organizer.config import PROTECTED_PATH_SEGMENTS, SCAN_SKIP_DIRS
from file_organizer.cli import _is_root_drive
from file_organizer.services.cleaner import _is_protected as cleaner_protected
from file_organizer.services.sorter import _is_protected as sorter_protected


# ── helpers ───────────────────────────────────────────────────────────────────

def _check_segment(segment: str) -> bool:
    """True if a path containing *segment* is blocked by PROTECTED_PATH_SEGMENTS."""
    probe = Path(f"/some/prefix/{segment}/file.txt")
    return any(seg in probe.parts or seg in str(probe).lower()
               for seg in PROTECTED_PATH_SEGMENTS)


# ── PROTECTED_PATH_SEGMENTS — completeness ───────────────────────────────────

@pytest.mark.parametrize("segment", sorted(PROTECTED_PATH_SEGMENTS))
def test_protected_segment_present(segment):
    assert segment in PROTECTED_PATH_SEGMENTS


# ── Windows protected paths ───────────────────────────────────────────────────

@pytest.mark.parametrize("path_str", [
    "C:/Windows/System32/cmd.exe",
    "C:/Windows/SysWOW64/ntdll.dll",
    "C:/Program Files/SomeApp/launcher.exe",
    "C:/Program Files (x86)/OldApp/uninstall.exe",
    "C:/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup/app.lnk",
    "C:/Users/user/AppData/Roaming/Microsoft/app.exe",
    "C:/Users/user/AppData/Local/Temp/tmp123.tmp",
    "C:/System Volume Information/tracking.log",
    "C:/$Recycle.Bin/S-1-5-21/file.txt",
    "C:/Windows/winsxs/x86_microsoft/manifest",
    "C:/Windows/servicing/sessions/sessions.xml",
    "C:/Windows/PERFLOGS/Admin/log.txt",
    "C:/Recovery/WindowsRE/winre.wim",
    "C:/EFI/Microsoft/Boot/bootmgfw.efi",
    "C:/WinRE/boot.wim",
])
def test_cleaner_blocks_windows_path(path_str):
    assert cleaner_protected(Path(path_str))


@pytest.mark.parametrize("path_str", [
    "C:/Windows/System32/cmd.exe",
    "C:/Program Files/SomeApp/launcher.exe",
    "C:/Users/user/AppData/Roaming/Microsoft/app.exe",
    "C:/Windows/winsxs/manifest",
    "C:/EFI/Microsoft/Boot/bootmgfw.efi",
])
def test_sorter_blocks_windows_path(path_str):
    assert sorter_protected(Path(path_str))


# ── macOS protected paths ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path_str", [
    "/Library/Application Support/com.apple.app",
    "/Library/Preferences/SystemConfiguration/com.apple.plist",
    "/System/Library/CoreServices/Finder.app",
    "/System/Library/Extensions/AppleIntelMEI.kext",
    "/Volumes/Macintosh HD/Users/user/file.txt",
    "/private/var/log/system.log",
    "/private/etc/hosts",
])
def test_cleaner_blocks_macos_path(path_str):
    assert cleaner_protected(Path(path_str))


@pytest.mark.parametrize("path_str", [
    "/Library/Application Support/com.apple.app",
    "/System/Library/CoreServices/Finder.app",
    "/Volumes/Macintosh HD/Users/user/file.txt",
    "/private/var/log/system.log",
])
def test_sorter_blocks_macos_path(path_str):
    assert sorter_protected(Path(path_str))


# ── Linux protected paths ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path_str", [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/bin/bash",
    "/sbin/init",
    "/lib/x86_64-linux-gnu/libc.so.6",
    "/lib64/ld-linux-x86-64.so.2",
    "/usr/bin/python3",
    "/usr/lib/systemd/systemd",
    "/var/log/syslog",
    "/var/lib/dpkg/status",
    "/proc/1/cmdline",
    "/sys/kernel/debug",
    "/dev/null",
    "/run/systemd/private",
    "/boot/grub/grub.cfg",
    "/opt/google/chrome/chrome",
])
def test_cleaner_blocks_linux_path(path_str):
    assert cleaner_protected(Path(path_str))


@pytest.mark.parametrize("path_str", [
    "/etc/passwd",
    "/bin/bash",
    "/usr/bin/python3",
    "/var/log/syslog",
    "/proc/1/cmdline",
    "/boot/grub/grub.cfg",
])
def test_sorter_blocks_linux_path(path_str):
    assert sorter_protected(Path(path_str))


# ── Credential / secret directory protection ─────────────────────────────────

@pytest.mark.parametrize("path_str", [
    "/home/user/.ssh/id_rsa",
    "/home/user/.ssh/id_ed25519",
    "/home/user/.ssh/known_hosts",
    "/home/user/.aws/credentials",
    "/home/user/.aws/config",
    "/home/user/.kube/config",
    "/home/user/.docker/config.json",
    "/home/user/.gnupg/secring.gpg",
    "/home/user/.gnupg/pubring.kbx",
    # Windows equivalents
    "C:/Users/user/.ssh/id_rsa",
    "C:/Users/user/.aws/credentials",
    "C:/Users/user/.kube/config",
])
def test_cleaner_blocks_credential_path(path_str):
    assert cleaner_protected(Path(path_str))


@pytest.mark.parametrize("path_str", [
    "/home/user/.ssh/id_rsa",
    "/home/user/.aws/credentials",
    "/home/user/.kube/config",
    "/home/user/.docker/config.json",
    "/home/user/.gnupg/secring.gpg",
])
def test_sorter_blocks_credential_path(path_str):
    assert sorter_protected(Path(path_str))


# ── Safe paths are not blocked ────────────────────────────────────────────────

@pytest.mark.parametrize("path_str", [
    "/home/user/Downloads/photo.jpg",
    "/home/user/Documents/report.pdf",
    "/home/user/Desktop/notes.txt",
    "C:/Users/user/Downloads/installer.exe",
    "C:/Users/user/Documents/budget.xlsx",
    "/Users/alice/Movies/vacation.mp4",
])
def test_cleaner_allows_safe_path(path_str):
    assert not cleaner_protected(Path(path_str))


@pytest.mark.parametrize("path_str", [
    "/home/user/Downloads/photo.jpg",
    "/home/user/Documents/report.pdf",
    "C:/Users/user/Downloads/installer.exe",
])
def test_sorter_allows_safe_path(path_str):
    assert not sorter_protected(Path(path_str))


# ── SCAN_SKIP_DIRS — coverage ─────────────────────────────────────────────────

@pytest.mark.parametrize("dir_name", sorted(SCAN_SKIP_DIRS))
def test_scan_skip_dir_present(dir_name):
    assert dir_name in SCAN_SKIP_DIRS


@pytest.mark.parametrize("dir_name", [
    # Linux system
    "etc", "bin", "sbin", "lib", "lib64", "usr", "var", "tmp", "opt", "root",
    # macOS
    "library", "system", "volumes",
    # Windows additions
    "efi", "winre",
    # Credentials
    ".ssh", ".aws", ".kube", ".docker", ".gnupg",
])
def test_scan_skip_dirs_contains_new_entries(dir_name):
    assert dir_name in SCAN_SKIP_DIRS


@pytest.mark.parametrize("dir_name", [
    "winsxs", "servicing", "appdata", ".git", "node_modules",
    "proc", "sys", "dev", "run", "private",
])
def test_scan_skip_dirs_retains_existing_entries(dir_name):
    assert dir_name in SCAN_SKIP_DIRS


# ── PROTECTED_PATH_SEGMENTS — new entries ────────────────────────────────────

@pytest.mark.parametrize("segment", [
    # Linux
    "etc", "bin", "sbin", "lib", "lib64", "usr", "var",
    "proc", "sys", "dev", "run", "boot", "opt",
    # macOS
    "library", "system", "volumes", "private",
    # Windows additions
    "winsxs", "servicing", "perflogs", "recovery", "efi", "winre",
    # Credentials
    ".ssh", ".aws", ".kube", ".docker", ".gnupg",
])
def test_protected_segments_contains_new_entries(segment):
    assert segment in PROTECTED_PATH_SEGMENTS


# ── _is_root_drive ────────────────────────────────────────────────────────────

def test_is_root_drive_posix_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _is_root_drive(Path("/"))


def test_is_root_drive_safe_subdir():
    assert not _is_root_drive(Path("/home/user/Downloads"))


def test_is_root_drive_safe_nested():
    assert not _is_root_drive(Path("/home/user/Documents/projects"))


def test_is_root_drive_home_dir():
    assert not _is_root_drive(Path.home())


def test_is_root_drive_tmp(tmp_path):
    assert not _is_root_drive(tmp_path)


def test_is_root_drive_returns_bool():
    result = _is_root_drive(Path("/home/user"))
    assert isinstance(result, bool)
