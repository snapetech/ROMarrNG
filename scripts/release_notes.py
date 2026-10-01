#!/usr/bin/env python3
"""Validate, preview, and assemble ROMarrNG release-note fragments."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

RELEASE_NOTE_DIRECTORY = "release-notes"
CATEGORIES = {
    "added": "Added",
    "changed": "Changed",
    "fixed": "Fixed",
    "security": "Security",
    "removed": "Removed",
    "deprecated": "Deprecated",
}
AUDIENCES = {"users", "operators"}
FRONTMATTER_KEYS = {"category", "audience", "area", "action", "breaking"}
ROOT = Path(__file__).resolve().parents[1]
FIRST_PUBLISHED_RELEASE = (0, 10, 0)


def git(*arguments: str, cwd: Path = ROOT, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode and check:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def is_release_note_path(filename: str) -> bool:
    path = PurePosixPath(filename)
    return (
        path.parent.as_posix() == RELEASE_NOTE_DIRECTORY
        and path.suffix == ".md"
        and path.name.lower() != "readme.md"
    )


def parse_release_note(filename: str, content: str) -> tuple[dict, list[str]]:
    errors: list[str] = []
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    frontmatter = re.match(r"^---\n([\s\S]*?)\n---\n?([\s\S]*)$", normalized)
    if not frontmatter:
        return {}, ["must contain YAML frontmatter delimited by `---`"]

    metadata: dict[str, str] = {}
    for line in frontmatter.group(1).split("\n"):
        if not line.strip():
            continue
        match = re.match(r"^([a-z][a-z-]*):\s*(\S.*)$", line)
        if not match:
            errors.append(f"has invalid frontmatter: {line}")
            continue
        key, value = match.group(1), match.group(2).strip()
        if key in metadata:
            errors.append(f'declares frontmatter key "{key}" more than once')
        metadata[key] = value

    for key in metadata:
        if key not in FRONTMATTER_KEYS:
            errors.append(f'frontmatter key "{key}" is not supported')

    category = metadata.get("category", "").lower()
    if category not in CATEGORIES:
        errors.append(f"category must be one of: {', '.join(CATEGORIES)}")

    audience_parts = [
        part.strip().lower()
        for part in metadata.get("audience", "").split(",")
        if part.strip()
    ]
    if (
        not audience_parts
        or any(part not in AUDIENCES for part in audience_parts)
        or len(set(audience_parts)) != len(audience_parts)
    ):
        errors.append("audience must list users, operators, or both exactly once")

    area = metadata.get("area", "").lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", area):
        errors.append(
            "area must be a 2-32 character lowercase slug such as `bookshelf` or `release-pipeline`"
        )

    action = re.sub(r"\s+", " ", metadata.get("action", "").strip())
    if not action:
        errors.append("action is required; use `none` when no action is needed")
    elif action.lower() != "none":
        if not 5 <= len(action) <= 200:
            errors.append("action must be 5-200 characters or exactly `none`")
        if re.search(r"(?:<!--|--!?>|\b(?:todo|tbd|fill in)\b)", action, re.I):
            errors.append("action contains a placeholder or HTML comment")

    breaking_value = metadata.get("breaking", "").lower()
    if breaking_value not in {"true", "false"}:
        errors.append("breaking must be either `true` or `false`")
    breaking = breaking_value == "true"
    if breaking and action.lower() == "none":
        errors.append("breaking changes must describe an upgrade or operator action")

    body = re.sub(r"\s+", " ", frontmatter.group(2).strip())
    if not 30 <= len(body) <= 400:
        errors.append("body must be 30-400 characters and describe the user impact")
    if re.search(r"(?:<!--|--!?>|\b(?:todo|tbd|fill in)\b)", body, re.I):
        errors.append("body contains a placeholder or HTML comment")
    if body and not re.match(r"^[A-Z0-9`*_]", body):
        errors.append("body must start with a capitalized sentence")
    if body and not re.search(r"[.!?)]$", body):
        errors.append("body must end with sentence punctuation")

    return {
        "file": filename,
        "category": category,
        "category_title": CATEGORIES.get(category, ""),
        "audience": audience_parts,
        "area": area,
        "action": "none" if action.lower() == "none" else action,
        "breaking": breaking,
        "body": body,
    }, errors


def changed_release_note_files(base: str, head: str) -> list[dict[str, str]]:
    output = git(
        "diff",
        "--name-status",
        "--find-renames",
        base,
        head,
        "--",
        RELEASE_NOTE_DIRECTORY,
    )
    entries: list[dict[str, str]] = []
    for line in output.splitlines():
        columns = line.split("\t")
        if len(columns) < 2:
            continue
        status = columns[0]
        filename = columns[-1]
        if is_release_note_path(filename):
            entries.append({"status": status[0], "file": filename})
    return entries


def latest_release_tag(head: str) -> str | None:
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", head],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def is_release_note_shipped(filename: str, head: str) -> bool:
    tag = latest_release_tag(head)
    if not tag:
        return False
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{tag}:{filename}"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def is_shipped_release_note_changed(filename: str, head: str) -> bool:
    tag = latest_release_tag(head)
    if not tag:
        return False
    shipped = subprocess.run(
        ["git", "show", f"{tag}:{filename}"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if shipped.returncode:
        return False
    current = subprocess.run(
        ["git", "show", f"{head}:{filename}"],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return current.returncode != 0 or current.stdout != shipped.stdout


def read_release_notes(entries: list[dict[str, str]]) -> tuple[list[dict], list[str]]:
    notes: list[dict] = []
    errors: list[str] = []
    for entry in entries:
        try:
            content = (ROOT / entry["file"]).read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"{entry['file']}: unable to read file ({error})")
            continue
        note, note_errors = parse_release_note(entry["file"], content)
        errors.extend(f"{entry['file']}: {error}" for error in note_errors)
        if not note_errors:
            notes.append(note)
    return notes, errors


def format_curated_notes(notes: list[dict]) -> str:
    if not notes:
        return ""
    lines = ["### User-facing changes", ""]
    for category, title in CATEGORIES.items():
        category_notes = [note for note in notes if note["category"] == category]
        if not category_notes:
            continue
        lines.extend([f"#### {title}", ""])
        for note in category_notes:
            area_title = " ".join(
                part.capitalize() for part in note["area"].split("-")
            )
            breaking_prefix = "**Breaking:** " if note["breaking"] else ""
            lines.append(
                f"- **{area_title}:** {breaking_prefix}{note['body']}"
            )
            if note["action"] != "none":
                lines.append(f"  - **Action required:** {note['action']}")
        lines.append("")
    return "\n".join(lines).strip()


def format_capture_metadata(notes: list[dict]) -> str:
    if not notes:
        return ""
    lines = [
        "### Capture metadata",
        "",
        "| Fragment | Audience | Area | Action | Breaking |",
        "| --- | --- | --- | --- | --- |",
    ]
    for note in notes:
        escape = lambda value: str(value).replace("|", r"\|")
        lines.append(
            f"| {escape(note['file'])} | {escape(', '.join(note['audience']))} | "
            f"{escape(note['area'])} | {escape(note['action'])} | "
            f"{'yes' if note['breaking'] else 'no'} |"
        )
    return "\n".join(lines)


def inject_curated_notes(changelog: str, curated_notes: str) -> str:
    if not curated_notes:
        return changelog
    heading = re.search(r"(?m)^## .+$", changelog)
    if not heading:
        return f"{curated_notes}\n\n{changelog.strip()}\n"

    tail_start = heading.end()
    tail = changelog[tail_start:]
    existing = re.search(
        r"(?ms)^### User-facing changes\s*\n.*?(?=^### |\Z)", tail
    )
    if existing:
        tail = tail[: existing.start()] + curated_notes + tail[existing.end() :]
        return f"{changelog[:tail_start]}\n\n{tail.lstrip()}"
    return (
        f"{changelog[:tail_start]}\n\n{curated_notes}\n"
        f"{tail.lstrip(chr(10))}"
    )


def validate_append_only(entries: list[dict[str, str]], head: str) -> list[str]:
    return [
        f"{entry['file']}: release-note fragments are append-only; add a new fragment instead of modifying a shipped one"
        for entry in entries
        if entry["status"] != "A"
        and is_shipped_release_note_changed(entry["file"], head)
    ]


def has_explicit_no_release_note(body: str) -> bool:
    return bool(
        re.search(r"release-note\s*:\s*none", body, re.I)
        or re.search(r"release-note-none-[a-z0-9-]+", body, re.I)
        or re.search(
            r"-\s*\[x\][^\n]*(?:internal-only|no user-facing release note)",
            body,
            re.I,
        )
    )


def notes_for_range(base: str, head: str) -> tuple[list[dict], list[str]]:
    entries = changed_release_note_files(base, head)
    notes, errors = read_release_notes(
        [
            entry
            for entry in entries
            if entry["status"] == "A"
            or not is_release_note_shipped(entry["file"], head)
        ]
    )
    return notes, [*validate_append_only(entries, head), *errors]


def append_summary(filename: str, content: str) -> None:
    with open(filename, "a", encoding="utf-8") as summary:
        summary.write(f"{content}\n")


def write_text(filename: str, content: str) -> None:
    Path(filename).write_text(content, encoding="utf-8")


def command_check(arguments: argparse.Namespace) -> int:
    notes, errors = notes_for_range(arguments.base, arguments.head)
    body = Path(arguments.pr_body).read_text(encoding="utf-8")
    explicit_none = has_explicit_no_release_note(body)
    issues = list(errors)
    if not notes and not explicit_none:
        issues.append(
            "add a validated file under release-notes/ or explicitly mark the PR `release-note: none` for internal-only work"
        )
    if notes and explicit_none and not arguments.allow_mixed_push_batch:
        issues.append(
            "choose either a release-note fragment or `release-note: none`; do not select both"
        )
    if issues:
        print("Release-note validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    if arguments.summary_file:
        summary = (
            "## Release-note preview\n\n"
            f"{format_curated_notes(notes)}\n\n{format_capture_metadata(notes)}"
            if notes
            else "## Release-note preview\n\nInternal-only change; no release note will be published."
        )
        append_summary(arguments.summary_file, summary)
    if notes:
        print(f"Validated {len(notes)} user-facing release-note fragment(s).")
    else:
        print("Explicitly marked as internal-only; no release note required.")
    return 0


def command_preview(arguments: argparse.Namespace) -> int:
    notes, errors = notes_for_range(arguments.base, arguments.head)
    if errors:
        print("Release-note preview failed validation:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not notes:
        print("No new release-note fragments were found in this range.")
        return 0
    print(format_curated_notes(notes))
    return 0


def command_assemble(arguments: argparse.Namespace) -> int:
    notes, errors = notes_for_range(arguments.previous_tag, arguments.head)
    if errors:
        print("Release-note assembly failed validation:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if not notes:
        print("The generated release notes contain no entries.", file=sys.stderr)
        return 1
    changelog = Path(arguments.changelog).read_text(encoding="utf-8")
    curated_notes = format_curated_notes(notes)
    if arguments.require_prepared_changelog:
        prepared = re.search(
            r"(?ms)^### User-facing changes\s*\n.*?(?=^### |\Z)", changelog
        )
        if not prepared or prepared.group(0).strip() != curated_notes:
            print(
                "CHANGELOG.md does not contain the generated notes for this release; "
                "run the release preparation command before tagging.",
                file=sys.stderr,
            )
            return 1
    write_text(arguments.output, inject_curated_notes(changelog, curated_notes))
    print(f"Added {len(notes)} curated release-note fragment(s) to {arguments.output}.")
    return 0


def prepend_changelog_section(current_path: str, existing_path: str, output_path: str) -> None:
    current = Path(current_path).read_text(encoding="utf-8").strip()
    existing = Path(existing_path).read_text(encoding="utf-8").strip()
    heading_match = re.search(r"(?m)^## (?!#).*$", current)
    version_match = (
        re.match(r"^## \[?v?(\d+\.\d+\.\d+)(?:\]|\s|$)", heading_match.group(0))
        if heading_match
        else None
    )
    if not heading_match or not version_match:
        raise ValueError("Current changelog does not contain a versioned release section.")
    version = version_match.group(1)

    headings = list(re.finditer(r"(?m)^## (?!#).*$", existing))
    first_heading = headings[0].start() if headings else len(existing)
    prefix = existing[:first_heading].rstrip()
    existing_version_heading = None
    for heading in headings:
        match = re.match(r"^## \[?v?(\d+\.\d+\.\d+)(?:\]|\s|$)", heading.group(0))
        if match and match.group(1) == version:
            existing_version_heading = heading
            break

    if existing_version_heading:
        following = next(
            (heading for heading in headings if heading.start() > existing_version_heading.start()),
            None,
        )
        section_end = following.start() if following else len(existing)
        updated = (
            existing[: existing_version_heading.start()]
            + current
            + "\n\n"
            + existing[section_end:].lstrip()
        )
        result = "Updated"
    else:
        history = existing[first_heading:].lstrip()
        updated = "\n\n".join(part for part in (prefix, current, history) if part)
        result = "Prepended"
    Path(output_path).write_text(f"{updated.strip()}\n", encoding="utf-8")
    print(f"{result} changelog section for v{version}.")


def command_prepare(arguments: argparse.Namespace) -> int:
    if not re.fullmatch(r"\d+\.\d+\.\d+", arguments.version):
        print("Version must use MAJOR.MINOR.PATCH.", file=sys.stderr)
        return 2
    if git("tag", "--list", f"v{arguments.version}").strip():
        print(
            f"v{arguments.version} is already tagged; released changelog sections are immutable.",
            file=sys.stderr,
        )
        return 1
    try:
        release_date = dt.date.fromisoformat(arguments.date)
    except ValueError:
        print("Date must use YYYY-MM-DD.", file=sys.stderr)
        return 2
    notes, errors = notes_for_range(arguments.previous_tag, arguments.head)
    if errors or not notes:
        print("Release changelog preparation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        if not notes:
            print("- no new release-note fragments were found", file=sys.stderr)
        return 1

    current = f"## [{arguments.version}] - {release_date.isoformat()}\n"
    current = inject_curated_notes(current, format_curated_notes(notes))
    current_file = Path(arguments.output)
    current_file.write_text(current.strip() + "\n", encoding="utf-8")
    prepend_changelog_section(
        arguments.output, arguments.changelog, arguments.changelog
    )
    print(f"Prepared CHANGELOG.md from {len(notes)} release-note fragment(s).")
    return 0


def command_check_changelog_tags(_: argparse.Namespace) -> int:
    tags = []
    for tag in git("tag", "--sort=version:refname", "--list", "v[0-9]*").splitlines():
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
        if match and tuple(map(int, match.groups())) >= FIRST_PUBLISHED_RELEASE:
            tags.append(tag)
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = re.findall(r"(?m)^## \[?(\d+\.\d+\.\d+)\]?(?:\s|$)", changelog)
    counts = {version: versions.count(version) for version in set(versions)}
    missing = [tag[1:] for tag in tags if counts.get(tag[1:], 0) == 0]
    duplicate = [
        f"{tag[1:]} ({counts[tag[1:]]} sections)"
        for tag in tags
        if counts.get(tag[1:], 0) > 1
    ]
    if missing or duplicate:
        if missing:
            print(f"Changelog is missing tagged releases: {', '.join(missing)}", file=sys.stderr)
        if duplicate:
            print(f"Changelog contains duplicate release sections: {', '.join(duplicate)}", file=sys.stderr)
        return 1
    print(f"Changelog covers all {len(tags)} ROMarrNG published release tag(s).")
    return 0


def split_discord_body(body: str, max_length: int = 3600) -> list[str]:
    if max_length < 1:
        raise ValueError("Maximum chunk length must be positive.")
    chunks: list[str] = []
    start = 0
    while start < len(body):
        limit = min(start + max_length, len(body))
        if limit == len(body):
            chunks.append(body[start:])
            break
        newline = body.rfind("\n", start, limit)
        end = newline + 1 if newline > start else limit
        chunks.append(body[start:end])
        start = end
    return chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate changed fragments or an explicit opt-out")
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--pr-body", required=True)
    check.add_argument("--summary-file")
    check.add_argument("--allow-mixed-push-batch", action="store_true")
    check.set_defaults(handler=command_check)

    preview = commands.add_parser("preview", help="render notes for a commit range")
    preview.add_argument("--base", required=True)
    preview.add_argument("--head", required=True)
    preview.set_defaults(handler=command_preview)

    assemble = commands.add_parser("assemble", help="inject fragments into a release body")
    assemble.add_argument("--previous-tag", required=True)
    assemble.add_argument("--head", required=True)
    assemble.add_argument("--changelog", required=True)
    assemble.add_argument("--output", required=True)
    assemble.add_argument("--require-prepared-changelog", action="store_true")
    assemble.set_defaults(handler=command_assemble)

    prepare = commands.add_parser("prepare", help="prepend a generated release section to CHANGELOG.md")
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--date", required=True)
    prepare.add_argument("--previous-tag", required=True)
    prepare.add_argument("--head", default="HEAD")
    prepare.add_argument("--changelog", default="CHANGELOG.md")
    prepare.add_argument("--output", default="/tmp/romarrng-release-section.md")
    prepare.set_defaults(handler=command_prepare)

    tags = commands.add_parser("check-changelog-tags", help="ensure every stable tag has one section")
    tags.set_defaults(handler=command_check_changelog_tags)

    split = commands.add_parser("split-discord", help="split stdin or a file into Discord-sized chunks")
    split.add_argument("--input")
    split.add_argument("--max-length", type=int, default=3600)
    split.set_defaults(handler=command_split_discord)
    return parser


def command_split_discord(arguments: argparse.Namespace) -> int:
    body = (
        Path(arguments.input).read_text(encoding="utf-8")
        if arguments.input
        else sys.stdin.read()
    )
    try:
        chunks = split_discord_body(body, arguments.max_length)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(chunks, ensure_ascii=False))
    return 0


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        return arguments.handler(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
