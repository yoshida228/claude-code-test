#!/usr/bin/env python3
"""TimeTree -> Google Calendar 同期スクリプト.

timetree-exporter が出力した ICS ファイルを読み取り、専用の
Google カレンダーへ予定を同期します。

設計方針:
- 同期先は「TimeTree 専用」の Google カレンダーを前提とする。
- 各予定には extendedProperties.private.timetree_uid に
  ICS の UID を保存し、同じ予定の更新・削除を判定する。
- timetree_uid を持たない予定（手動で入れた予定など）は消さない。
- 繰り返し予定は展開せず、RRULE をそのまま Google へ渡す。

使い方:
  python sync.py --ics timetree.ics            # 実際に同期
  python sync.py --ics timetree.ics --dry-run  # 変更内容の表示のみ

必要な環境変数（実際の同期時）:
  GOOGLE_CALENDAR_ID            同期先カレンダーの ID
  GOOGLE_SERVICE_ACCOUNT_JSON   サービスアカウント鍵 JSON の中身そのもの
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field


# ---------------------------------------------------------------- ICS 解析
# ICS (RFC 5545) の VEVENT を標準ライブラリだけで最小限パースする。

def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_params(segment: str) -> tuple[str, dict[str, str]]:
    parts = segment.split(";")
    name = parts[0].strip().upper()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, val = part.split("=", 1)
            params[key.strip().upper()] = val.strip()
    return name, params


@dataclass
class IcsEvent:
    uid: str
    summary: str = ""
    description: str = ""
    location: str = ""
    dtstart_raw: str = ""
    dtstart_params: dict[str, str] = field(default_factory=dict)
    dtend_raw: str = ""
    dtend_params: dict[str, str] = field(default_factory=dict)
    rrule: str = ""


def parse_ics(text: str) -> list[IcsEvent]:
    events: list[IcsEvent] = []
    current: IcsEvent | None = None
    for line in _unfold(text):
        if not line.strip():
            continue
        if line.strip().upper() == "BEGIN:VEVENT":
            current = IcsEvent(uid="")
            continue
        if line.strip().upper() == "END:VEVENT":
            if current is not None and current.uid:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, params = _parse_params(head)
        value = value.strip()
        if name == "UID":
            current.uid = value
        elif name == "SUMMARY":
            current.summary = _unescape(value)
        elif name == "DESCRIPTION":
            current.description = _unescape(value)
        elif name == "LOCATION":
            current.location = _unescape(value)
        elif name == "DTSTART":
            current.dtstart_raw, current.dtstart_params = value, params
        elif name == "DTEND":
            current.dtend_raw, current.dtend_params = value, params
        elif name == "RRULE":
            current.rrule = value
    return events


# ------------------------------------------------------- Google 形式へ変換

def _google_datetime(raw: str, params: dict[str, str]) -> dict:
    """ICS の日時文字列を Google Calendar API の形式へ変換する。"""
    raw = raw.strip()
    tzid = params.get("TZID")
    # 終日予定: 20260101
    if re.fullmatch(r"\d{8}", raw):
        return {"date": f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"}
    # 時刻付き: 20260101T090000 / 20260101T090000Z
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)", raw)
    if not m:
        raise ValueError(f"対応できない日時形式です: {raw!r}")
    y, mo, d, h, mi, s, z = m.groups()
    base = f"{y}-{mo}-{d}T{h}:{mi}:{s}"
    if z == "Z":
        return {"dateTime": base + "Z"}
    if tzid:
        return {"dateTime": base, "timeZone": tzid}
    # タイムゾーン指定なしは Asia/Tokyo として扱う（日本の利用を想定）
    return {"dateTime": base, "timeZone": "Asia/Tokyo"}


def to_google_event(ev: IcsEvent) -> dict:
    body: dict = {
        "summary": ev.summary or "(無題)",
        "extendedProperties": {"private": {"timetree_uid": ev.uid}},
    }
    if ev.description:
        body["description"] = ev.description
    if ev.location:
        body["location"] = ev.location
    body["start"] = _google_datetime(ev.dtstart_raw, ev.dtstart_params)
    if ev.dtend_raw:
        body["end"] = _google_datetime(ev.dtend_raw, ev.dtend_params)
    else:
        body["end"] = dict(body["start"])
    if ev.rrule:
        body["recurrence"] = [f"RRULE:{ev.rrule}"]
    return body


# ------------------------------------------------------------------- 同期

def _comparable(body: dict) -> str:
    keys = ("summary", "description", "location", "start", "end", "recurrence")
    return json.dumps({k: body.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)


def plan_sync(ics_events: list[IcsEvent], google_events: list[dict]) -> dict:
    """ICS と既存の Google 予定から、追加/更新/削除の計画を作る。"""
    existing_by_uid: dict[str, dict] = {}
    for g in google_events:
        uid = (
            g.get("extendedProperties", {})
            .get("private", {})
            .get("timetree_uid")
        )
        if uid:
            existing_by_uid[uid] = g

    plan = {"insert": [], "update": [], "delete": [], "unchanged": 0}
    seen_uids: set[str] = set()
    for ev in ics_events:
        seen_uids.add(ev.uid)
        body = to_google_event(ev)
        current = existing_by_uid.get(ev.uid)
        if current is None:
            plan["insert"].append(body)
            continue
        current_body = {
            "summary": current.get("summary"),
            "description": current.get("description"),
            "location": current.get("location"),
            "start": current.get("start"),
            "end": current.get("end"),
            "recurrence": current.get("recurrence"),
        }
        if _comparable(body) != _comparable(current_body):
            plan["update"].append({"id": current["id"], "body": body})
        else:
            plan["unchanged"] += 1

    for uid, g in existing_by_uid.items():
        if uid not in seen_uids:
            plan["delete"].append({"id": g["id"], "summary": g.get("summary", "")})
    return plan


def _google_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise SystemExit("環境変数 GOOGLE_SERVICE_ACCOUNT_JSON が未設定です")
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _list_google_events(service, calendar_id: str) -> list[dict]:
    events: list[dict] = []
    token = None
    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                maxResults=2500,
                pageToken=token,
                singleEvents=False,
            )
            .execute()
        )
        events.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            return events


def main() -> int:
    parser = argparse.ArgumentParser(description="TimeTree -> Google Calendar 同期")
    parser.add_argument("--ics", required=True, help="timetree-exporter が出力した ICS ファイル")
    parser.add_argument("--dry-run", action="store_true", help="変更内容を表示するだけで実行しない")
    args = parser.parse_args()

    with open(args.ics, encoding="utf-8") as f:
        ics_events = parse_ics(f.read())
    print(f"ICS の予定: {len(ics_events)} 件")

    if args.dry_run:
        for ev in ics_events:
            body = to_google_event(ev)
            print(f"  - {body['summary']} / start={body['start']} / uid={ev.uid}")
        print("dry-run のため Google カレンダーへは接続していません")
        return 0

    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "")
    if not calendar_id:
        raise SystemExit("環境変数 GOOGLE_CALENDAR_ID が未設定です")

    service = _google_service()
    google_events = _list_google_events(service, calendar_id)
    plan = plan_sync(ics_events, google_events)
    print(
        f"計画: 追加 {len(plan['insert'])} / 更新 {len(plan['update'])} / "
        f"削除 {len(plan['delete'])} / 変更なし {plan['unchanged']}"
    )

    for body in plan["insert"]:
        service.events().insert(calendarId=calendar_id, body=body).execute()
    for item in plan["update"]:
        service.events().update(
            calendarId=calendar_id, eventId=item["id"], body=item["body"]
        ).execute()
    for item in plan["delete"]:
        service.events().delete(calendarId=calendar_id, eventId=item["id"]).execute()
    print("同期が完了しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
