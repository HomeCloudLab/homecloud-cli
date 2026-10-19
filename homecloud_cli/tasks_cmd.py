"""Tasks CLI — Jira-like full management over the console Tasks API."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from homecloud_core.errors import HomeCloudError

from homecloud_cli.output import emit

_DUE_RELATIVE = re.compile(r"^\+(\d+)([dw]?)$", re.I)


def _output_option(value: str) -> str:
    from homecloud_cli.cli import _output_option as _opt

    return _opt(value)


def _client(profile: Optional[str]):
    from homecloud_cli.cli import _client as _c

    return _c(profile)


def _handle_error(exc: BaseException) -> None:
    from homecloud_cli.cli import _handle_error as _h

    _h(exc)


def parse_due_at(raw: str | None) -> str | None:
    """Parse ISO-8601 or relative: today, tomorrow, +3d, +1w."""
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    lower = value.lower()
    now = datetime.now(UTC)
    if lower in {"today", "היום"}:
        return now.replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
    if lower in {"tomorrow", "מחר"}:
        day = now + timedelta(days=1)
        return day.replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
    m = _DUE_RELATIVE.match(value)
    if m:
        n = int(m.group(1))
        unit = (m.group(2) or "d").lower()
        delta = timedelta(weeks=n) if unit == "w" else timedelta(days=n)
        day = now + delta
        return day.replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
    return value


def flatten_task_row(item: dict[str, Any]) -> dict[str, Any]:
    assignees = item.get("assignees") or ([] if not item.get("assignee") else [item["assignee"]])
    names = [a.get("username") for a in assignees if isinstance(a, dict) and a.get("username")]
    labels = item.get("labels") or []
    label_names = [lb.get("name") for lb in labels if isinstance(lb, dict) and lb.get("name")]
    return {
        "key": item.get("key"),
        "title": item.get("title"),
        "type": item.get("type"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "assignee": ", ".join(names) if names else "",
        "labels": ", ".join(label_names) if label_names else "",
        "due_at": item.get("due_at") or "",
        "unread": item.get("unread_count") or 0,
    }


def flatten_activity_row(ev: dict[str, Any]) -> dict[str, Any]:
    actor = ev.get("actor") if isinstance(ev.get("actor"), dict) else {}
    payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    summary = payload.get("body") or payload.get("comment") or ""
    if not summary and payload:
        summary = ", ".join(f"{k}={v}" for k, v in list(payload.items())[:4])
    return {
        "created_at": ev.get("created_at"),
        "event_type": ev.get("event_type"),
        "actor": actor.get("username") if actor else "",
        "summary": (summary or "")[:80],
        "id": ev.get("id"),
    }


def _load_description(
    description: str | None,
    description_file: Path | None,
) -> tuple[str | None, str | None]:
    if description_file is not None and description is not None:
        raise HomeCloudError("pass either --description or --description-file, not both")
    if description_file is not None:
        text = description_file.read_text(encoding="utf-8")
        fmt = "markdown" if description_file.suffix.lower() in {".md", ".markdown"} else "plain"
        return text, fmt
    return description, None


def register_tasks_commands(tasks_app: typer.Typer) -> None:
    @tasks_app.command("search")
    def tasks_search(
        query: Annotated[
            Optional[list[str]],
            typer.Argument(
                help="Smart query: text @user &label #service type:change due:overdue",
            ),
        ] = None,
        status: Annotated[
            Optional[str],
            typer.Option("--status", help="Comma-separated statuses"),
        ] = None,
        assignee: Annotated[Optional[str], typer.Option("--assignee", help="me | user id")] = None,
        watcher: Annotated[Optional[str], typer.Option("--watcher", help="me")] = None,
        label: Annotated[Optional[str], typer.Option("--label")] = None,
        type: Annotated[Optional[str], typer.Option("--type")] = None,
        archived: Annotated[bool, typer.Option("--archived")] = False,
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        """Smart search (same grammar as the console search box)."""
        try:
            q = " ".join(query) if query else None
            items = _client(profile).tasks.search(
                q or "",
                status=status,
                assignee=assignee,
                watcher=watcher,
                label=label,
                type=type,
                archived=archived,
            )
            rows = [flatten_task_row(i) for i in items]
            emit(
                rows if output == "table" else items,
                output_format=_output_option(output),
                columns=["key", "title", "status", "priority", "assignee", "labels", "due_at"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("list")
    def tasks_list(
        query: Annotated[
            Optional[list[str]],
            typer.Argument(help="Optional smart query (same as search)"),
        ] = None,
        type: Annotated[Optional[str], typer.Option("--type")] = None,
        status: Annotated[Optional[str], typer.Option("--status")] = None,
        assignee: Annotated[Optional[str], typer.Option("--assignee", help="me | user id")] = None,
        watcher: Annotated[Optional[str], typer.Option("--watcher")] = None,
        label: Annotated[Optional[str], typer.Option("--label")] = None,
        project_id: Annotated[Optional[str], typer.Option("--project-id")] = None,
        q: Annotated[Optional[str], typer.Option("--q", help="Smart query string")] = None,
        due: Annotated[Optional[str], typer.Option("--due")] = None,
        mine: Annotated[bool, typer.Option("--mine", help="Shortcut for --assignee me")] = False,
        watching: Annotated[bool, typer.Option("--watching", help="Shortcut for --watcher me")] = False,
        archived: Annotated[bool, typer.Option("--archived")] = False,
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        """List or search tasks. Use --mine / smart query for Jira-like filters."""
        try:
            combined = q
            if query:
                joined = " ".join(query)
                combined = f"{combined} {joined}".strip() if combined else joined
            items = _client(profile).tasks.list(
                type=type,
                status=status,
                assignee="me" if mine else assignee,
                watcher="me" if watching else watcher,
                label=label,
                project_id=project_id,
                q=combined,
                due=due,
                archived=archived,
            )
            rows = [flatten_task_row(i) for i in items]
            emit(
                rows if output == "table" else items,
                output_format=_output_option(output),
                columns=["key", "title", "type", "status", "priority", "assignee", "labels", "due_at"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("mine")
    def tasks_mine(
        status: Annotated[Optional[str], typer.Option("--status")] = None,
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        """Items assigned to you."""
        try:
            items = _client(profile).tasks.list(assignee="me", status=status)
            rows = [flatten_task_row(i) for i in items]
            emit(
                rows if output == "table" else items,
                output_format=_output_option(output),
                columns=["key", "title", "status", "priority", "labels", "due_at"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("get")
    def tasks_get(
        key: Annotated[str, typer.Argument(help="TASK-12")],
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Show one item (marks discussion seen, like opening in the console)."""
        try:
            emit(_client(profile).tasks.get(key), output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("create")
    def tasks_create(
        title: Annotated[str, typer.Argument(help="Title")],
        type: Annotated[str, typer.Option("--type")] = "task",
        description: Annotated[Optional[str], typer.Option("--description", "-d")] = None,
        description_file: Annotated[
            Optional[Path],
            typer.Option("--description-file", exists=True, readable=True),
        ] = None,
        description_format: Annotated[
            Optional[str],
            typer.Option("--description-format", help="plain|markdown"),
        ] = None,
        assignee: Annotated[
            Optional[list[str]],
            typer.Option("--assignee", "-a", help="Username, @user, me, or UUID (repeatable)"),
        ] = None,
        priority: Annotated[Optional[str], typer.Option("--priority")] = None,
        severity: Annotated[Optional[str], typer.Option("--severity")] = None,
        due: Annotated[
            Optional[str],
            typer.Option("--due", help="ISO-8601, today, tomorrow, +3d, +1w"),
        ] = None,
        label: Annotated[
            Optional[list[str]],
            typer.Option("--label", "-l", help="Label name (repeatable)"),
        ] = None,
        service: Annotated[
            Optional[list[str]],
            typer.Option("--service", help="Linked service name (repeatable)"),
        ] = None,
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Create a task — assignees by username, labels by name, smart --due."""
        try:
            body, auto_fmt = _load_description(description, description_file)
            fmt = description_format or auto_fmt
            result = _client(profile).tasks.create(
                title,
                type=type,
                description=body,
                description_format=fmt,
                assignees=assignee,
                priority=priority,
                severity=severity,
                due_at=parse_due_at(due),
                label_names=label,
                services=service,
            )
            emit(result, output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    def _tasks_update(
        key: str,
        title: Optional[str],
        description: Optional[str],
        description_file: Optional[Path],
        description_format: Optional[str],
        type: Optional[str],
        status: Optional[str],
        assignee: Optional[list[str]],
        clear_assignee: bool,
        due: Optional[str],
        clear_due: bool,
        priority: Optional[str],
        severity: Optional[str],
        assign_me: bool,
        profile: Optional[str],
        output: str,
    ) -> None:
        try:
            body, auto_fmt = _load_description(description, description_file)
            fields: dict[str, Any] = {}
            if title is not None:
                fields["title"] = title
            if body is not None:
                fields["description"] = body
            fmt = description_format or auto_fmt
            if fmt is not None:
                fields["description_format"] = fmt
            if type is not None:
                fields["type"] = type
            if status is not None:
                fields["status"] = status
            if assign_me:
                fields["assignees"] = ["me"]
            elif assignee is not None:
                fields["assignees"] = assignee
            if clear_assignee:
                fields["clear_assignee"] = True
            if due is not None:
                fields["due_at"] = parse_due_at(due)
            if clear_due:
                fields["clear_due"] = True
            if priority is not None:
                fields["priority"] = priority
            if severity is not None:
                fields["severity"] = severity
            if not fields:
                raise HomeCloudError("pass at least one field to update")
            result = _client(profile).tasks.update(key, **fields)
            emit(result, output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("update")
    def tasks_update(
        key: Annotated[str, typer.Argument(help="TASK-12")],
        title: Annotated[Optional[str], typer.Option("--title")] = None,
        description: Annotated[Optional[str], typer.Option("--description", "-d")] = None,
        description_file: Annotated[
            Optional[Path],
            typer.Option("--description-file", exists=True, readable=True),
        ] = None,
        description_format: Annotated[Optional[str], typer.Option("--description-format")] = None,
        type: Annotated[Optional[str], typer.Option("--type")] = None,
        status: Annotated[Optional[str], typer.Option("--status", "-s")] = None,
        assignee: Annotated[
            Optional[list[str]],
            typer.Option("--assignee", "-a", help="Replace assignees (username/me/UUID)"),
        ] = None,
        clear_assignee: Annotated[bool, typer.Option("--clear-assignee")] = False,
        due: Annotated[Optional[str], typer.Option("--due")] = None,
        clear_due: Annotated[bool, typer.Option("--clear-due")] = False,
        priority: Annotated[Optional[str], typer.Option("--priority")] = None,
        severity: Annotated[Optional[str], typer.Option("--severity")] = None,
        assign_me: Annotated[bool, typer.Option("--assign-me", help="Assign to yourself")] = False,
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Update fields. Status follows console assignee rules."""
        _tasks_update(
            key,
            title,
            description,
            description_file,
            description_format,
            type,
            status,
            assignee,
            clear_assignee,
            due,
            clear_due,
            priority,
            severity,
            assign_me,
            profile,
            output,
        )

    @tasks_app.command("patch")
    def tasks_patch(
        key: Annotated[str, typer.Argument(help="TASK-12")],
        title: Annotated[Optional[str], typer.Option("--title")] = None,
        description: Annotated[Optional[str], typer.Option("--description", "-d")] = None,
        description_file: Annotated[
            Optional[Path],
            typer.Option("--description-file", exists=True, readable=True),
        ] = None,
        description_format: Annotated[Optional[str], typer.Option("--description-format")] = None,
        type: Annotated[Optional[str], typer.Option("--type")] = None,
        status: Annotated[Optional[str], typer.Option("--status", "-s")] = None,
        assignee: Annotated[
            Optional[list[str]],
            typer.Option("--assignee", "-a", help="Replace assignees (username/me/UUID)"),
        ] = None,
        clear_assignee: Annotated[bool, typer.Option("--clear-assignee")] = False,
        due: Annotated[Optional[str], typer.Option("--due")] = None,
        clear_due: Annotated[bool, typer.Option("--clear-due")] = False,
        priority: Annotated[Optional[str], typer.Option("--priority")] = None,
        severity: Annotated[Optional[str], typer.Option("--severity")] = None,
        assign_me: Annotated[bool, typer.Option("--assign-me", help="Assign to yourself")] = False,
        profile: Annotated[Optional[str], typer.Option(help="Profile name")] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Alias for ``update``."""
        _tasks_update(
            key,
            title,
            description,
            description_file,
            description_format,
            type,
            status,
            assignee,
            clear_assignee,
            due,
            clear_due,
            priority,
            severity,
            assign_me,
            profile,
            output,
        )

    @tasks_app.command("assign")
    def tasks_assign(
        key: Annotated[str, typer.Argument()],
        users: Annotated[list[str], typer.Argument(help="Usernames / me / UUIDs")],
        status: Annotated[Optional[str], typer.Option("--status")] = None,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Replace assignees (and optionally set status in one request)."""
        try:
            fields: dict[str, Any] = {"assignees": users}
            if status is not None:
                fields["status"] = status
            emit(_client(profile).tasks.update(key, **fields), output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("assign-me")
    def tasks_assign_me(
        key: Annotated[str, typer.Argument()],
        status: Annotated[Optional[str], typer.Option("--status")] = None,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Assign to yourself (optionally set status)."""
        try:
            emit(
                _client(profile).tasks.assign_me(key, status=status),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("unassign")
    def tasks_unassign(
        key: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(_client(profile).tasks.unassign(key), output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("comment")
    def tasks_comment(
        key: Annotated[str, typer.Argument()],
        body: Annotated[
            Optional[str],
            typer.Argument(help="Comment text (or use --file)"),
        ] = None,
        file: Annotated[
            Optional[Path],
            typer.Option("--file", "-f", exists=True, readable=True),
        ] = None,
        quote: Annotated[Optional[str], typer.Option("--quote", help="Quote comment id")] = None,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Add a discussion comment."""
        try:
            if file is not None and body:
                raise HomeCloudError("pass body or --file, not both")
            text = file.read_text(encoding="utf-8") if file is not None else body
            if not text or not str(text).strip():
                raise HomeCloudError("comment body is required")
            emit(
                _client(profile).tasks.comment(key, text, quote_comment_id=quote),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("comment-edit")
    def tasks_comment_edit(
        key: Annotated[str, typer.Argument()],
        comment_id: Annotated[str, typer.Argument()],
        body: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(
                _client(profile).tasks.comment_update(key, comment_id, body),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("comment-delete")
    def tasks_comment_delete(
        key: Annotated[str, typer.Argument()],
        comment_id: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(
                _client(profile).tasks.comment_delete(key, comment_id),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("activity")
    def tasks_activity(
        key: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        """Discussion + system events (comments, status, assign, …)."""
        try:
            items = _client(profile).tasks.activity(key)
            rows = [flatten_activity_row(e) for e in items]
            emit(
                rows if output == "table" else items,
                output_format=_output_option(output),
                columns=["created_at", "event_type", "actor", "summary"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("watch")
    def tasks_watch(
        key: Annotated[str, typer.Argument()],
        user: Annotated[str, typer.Option("--user", help="Username or me")] = "me",
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(_client(profile).tasks.watch(key, user), output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("unwatch")
    def tasks_unwatch(
        key: Annotated[str, typer.Argument()],
        user: Annotated[str, typer.Option("--user")] = "me",
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(_client(profile).tasks.unwatch(key, user), output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("label")
    def tasks_label(
        key: Annotated[str, typer.Argument()],
        name: Annotated[str, typer.Argument(help="Label name (created if missing)")],
        color: Annotated[Optional[str], typer.Option("--color")] = None,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Attach a label by name (creates catalog entry if needed)."""
        try:
            emit(
                _client(profile).tasks.add_label(key, name, color=color),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("unlabel")
    def tasks_unlabel(
        key: Annotated[str, typer.Argument()],
        label_id: Annotated[str, typer.Argument(help="Label id")],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(
                _client(profile).tasks.remove_label(key, label_id),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("labels")
    def tasks_labels(
        include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        """List account label catalog."""
        try:
            items = _client(profile).tasks.labels(include_archived=include_archived)
            emit(
                items,
                output_format=_output_option(output),
                columns=["name", "color", "archived", "id"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("people")
    def tasks_people(
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        """Assignable account members."""
        try:
            items = _client(profile).tasks.people()
            emit(
                items,
                output_format=_output_option(output),
                columns=["username", "email", "id"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("archive")
    def tasks_archive(
        key: Annotated[str, typer.Argument()],
        cancel: Annotated[
            bool,
            typer.Option("--cancel", help="Cancel then archive (for open items)"),
        ] = False,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(
                _client(profile).tasks.archive(key, cancel=cancel),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("restore")
    def tasks_restore(
        key: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(_client(profile).tasks.restore(key), output_format=_output_option(output))
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("delete")
    def tasks_delete(
        key: Annotated[str, typer.Argument()],
        yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm delete")] = False,
        profile: Annotated[Optional[str], typer.Option()] = None,
    ) -> None:
        """Permanently delete (requires tasks.delete)."""
        try:
            if not yes:
                raise HomeCloudError("refusing to delete without --yes")
            _client(profile).tasks.delete(key)
            typer.echo(f"Deleted {key}")
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("link")
    def tasks_link(
        key: Annotated[str, typer.Argument()],
        resource_type: Annotated[str, typer.Option("--type", help="compute|mdb|domains|…")],
        resource_id: Annotated[str, typer.Option("--id")],
        resource_ref: Annotated[str, typer.Option("--ref", help="Display ref")] = "",
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(
                _client(profile).tasks.link_resource(
                    key,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    resource_ref=resource_ref,
                ),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("unlink")
    def tasks_unlink(
        key: Annotated[str, typer.Argument()],
        link_id: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        try:
            emit(
                _client(profile).tasks.unlink_resource(key, link_id),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("share")
    def tasks_share(
        key: Annotated[str, typer.Argument()],
        expires_in: Annotated[
            str,
            typer.Option("--expires-in", help="never|7d|30d"),
        ] = "never",
        label: Annotated[Optional[str], typer.Option("--label")] = None,
        include_discussion: Annotated[bool, typer.Option("--include-discussion")] = False,
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "json",
    ) -> None:
        """Create a view-only public share link (URL shown once)."""
        try:
            emit(
                _client(profile).tasks.create_share(
                    key,
                    expires_in=expires_in,
                    label=label,
                    include_discussion=include_discussion,
                ),
                output_format=_output_option(output),
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("shares")
    def tasks_shares(
        key: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
        output: Annotated[str, typer.Option("--output", "-o")] = "table",
    ) -> None:
        try:
            items = _client(profile).tasks.list_shares(key)
            emit(
                items,
                output_format=_output_option(output),
                columns=["id", "label", "expires_at", "revoked_at", "created_at"],
            )
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)

    @tasks_app.command("unshare")
    def tasks_unshare(
        key: Annotated[str, typer.Argument()],
        share_id: Annotated[str, typer.Argument()],
        profile: Annotated[Optional[str], typer.Option()] = None,
    ) -> None:
        try:
            _client(profile).tasks.revoke_share(key, share_id)
            typer.echo(f"Revoked share {share_id}")
        except (HomeCloudError, FileNotFoundError, ValueError) as exc:
            _handle_error(exc)
