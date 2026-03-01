#!/usr/bin/env python3
"""
WhatsApp message log extractor.

Reads whatsapp-lite session JSONL files and writes structured logs
to daily memory files (memory/YYYY-MM-DD.md).

With --employee-logs, also writes per-employee WhatsApp transcripts
into team/<slug>.md files under the Activity Log section.

Usage:
    python3 scripts/whatsapp-log.py [--date YYYY-MM-DD] [--dry-run] [--employee-logs]
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta

# WITA = UTC+8
WITA = timezone(timedelta(hours=8))

BASE_DIR = "/Users/ai/openclaw/workspace"
SESSIONS_DIR = "/Users/ai/openclaw/agents/whatsapp-lite/sessions"
SESSIONS_INDEX = os.path.join(SESSIONS_DIR, "sessions.json")
ALIASES_FILE = os.path.join(BASE_DIR, "team/_aliases.json")
TEAM_DIR = os.path.join(BASE_DIR, "team")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")


def load_aliases():
    """Load phone-to-name mapping from _aliases.json."""
    phone_map = {}
    try:
        with open(ALIASES_FILE) as f:
            data = json.load(f)
        for _key, val in data.items():
            phone = val.get("phone")
            if phone:
                phone_map[phone] = val.get("first", val.get("short", phone))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return phone_map


def resolve_name(phone_or_name, phone_map):
    """Resolve a phone number or display name to canonical first name."""
    if not phone_or_name:
        return "Unknown"
    # Direct phone lookup
    if phone_or_name in phone_map:
        return phone_map[phone_or_name]
    # Try extracting phone from "Name (+phone)" format
    m = re.search(r'\((\+\d+)\)', phone_or_name)
    if m and m.group(1) in phone_map:
        return phone_map[m.group(1)]
    # Try matching by display name against aliases
    return phone_or_name


def parse_group_message_text(text):
    """Parse metadata blocks from a group user message.

    Returns dict with keys: group_subject, sender_name, sender_phone,
    chat_history (list), actual_text, media_path.
    """
    result = {
        "group_subject": None,
        "sender_name": None,
        "sender_phone": None,
        "chat_history": [],
        "actual_text": "",
        "media_path": None,
    }

    # Extract media attachment
    media_match = re.search(r'\[media attached: ([^\]]+)\]', text)
    if media_match:
        path = media_match.group(1)
        ext = path.rsplit('.', 1)[-1] if '.' in path else ''
        media_type = path.split('(')[-1].rstrip(')') if '(' in path else ext
        # Extract just the file type from "path (mime/type)"
        mime_match = re.search(r'\(([^)]+)\)', media_match.group(0))
        if mime_match:
            media_type = mime_match.group(1)
        result["media_path"] = path.split(' (')[0]  # path without mime

    # Extract conversation info
    conv_match = re.search(
        r'Conversation info \(untrusted metadata\):\s*```json\s*(\{[^}]+\})\s*```',
        text, re.DOTALL
    )
    if conv_match:
        try:
            conv = json.loads(conv_match.group(1))
            result["group_subject"] = conv.get("group_subject")
        except json.JSONDecodeError:
            pass

    # Extract sender info
    sender_match = re.search(
        r'Sender \(untrusted metadata\):\s*```json\s*(\{[^}]+\})\s*```',
        text, re.DOTALL
    )
    if sender_match:
        try:
            sender = json.loads(sender_match.group(1))
            result["sender_name"] = sender.get("name")
            result["sender_phone"] = sender.get("e164")
        except json.JSONDecodeError:
            pass

    # Extract chat history
    history_match = re.search(
        r'Chat history since last reply \(untrusted, for context\):\s*```json\s*(\[[\s\S]*?\])\s*```',
        text
    )
    if history_match:
        try:
            result["chat_history"] = json.loads(history_match.group(1))
        except json.JSONDecodeError:
            pass

    # Extract actual message text (after all metadata blocks)
    # The actual message is after the last ``` block, or after <media:image>
    parts = re.split(r'```\s*\n?', text)
    if len(parts) > 1:
        remainder = parts[-1].strip()
        # Remove <media:image> or similar tags
        remainder = re.sub(r'<media:\w+>', '', remainder).strip()
        # Remove the media instruction line
        remainder = re.sub(
            r'To send an image back.*?Keep caption in the text body\.\s*',
            '', remainder, flags=re.DOTALL
        ).strip()
        result["actual_text"] = remainder
    else:
        result["actual_text"] = text.strip()

    return result


def parse_dm_message_text(text):
    """Parse metadata from a DM user message.

    Returns dict with keys: sender_phone, actual_text, media_path.
    """
    result = {
        "sender_phone": None,
        "actual_text": "",
        "media_path": None,
    }

    # Extract media
    media_match = re.search(r'\[media attached: ([^\]]+)\]', text)
    if media_match:
        result["media_path"] = media_match.group(0).split(': ')[1].split(' (')[0]

    # Extract sender phone from conversation info
    conv_match = re.search(
        r'Conversation info \(untrusted metadata\):\s*```json\s*(\{[^}]+\})\s*```',
        text, re.DOTALL
    )
    if conv_match:
        try:
            conv = json.loads(conv_match.group(1))
            result["sender_phone"] = conv.get("sender")
        except json.JSONDecodeError:
            pass

    # Extract actual text - everything after metadata blocks
    # Remove system messages, metadata blocks, media instructions
    cleaned = text
    # Remove system lines
    cleaned = re.sub(r'System: \[[^\]]+\][^\n]*\n?', '', cleaned)
    # Remove queued message headers
    cleaned = re.sub(r'\[Queued messages while agent was busy\]\s*---\s*Queued #\d+\s*', '', cleaned)
    # Remove conversation info blocks
    cleaned = re.sub(
        r'Conversation info \(untrusted metadata\):\s*```json\s*\{[^}]+\}\s*```\s*',
        '', cleaned, flags=re.DOTALL
    )
    # Remove media instructions
    cleaned = re.sub(
        r'\[media attached:[^\]]+\]\s*To send an image back.*?Keep caption in the text body\.\s*',
        '[media] ', cleaned, flags=re.DOTALL
    )
    cleaned = re.sub(r'<media:\w+>\s*', '', cleaned)

    result["actual_text"] = cleaned.strip()
    return result


def ts_to_wita(ts_str):
    """Convert ISO timestamp string to WITA datetime."""
    # Handle both "2026-02-18T02:04:26.305Z" and epoch ms
    if isinstance(ts_str, (int, float)):
        return datetime.fromtimestamp(ts_str / 1000, tz=WITA)
    ts_str = ts_str.replace('Z', '+00:00')
    dt = datetime.fromisoformat(ts_str)
    return dt.astimezone(WITA)


def ms_to_wita(ms):
    """Convert epoch milliseconds to WITA datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=WITA)


def clean_text(text):
    """Collapse newlines into spaces and strip, preserving full content."""
    if not text:
        return ""
    return text.replace('\n', ' ').strip()


def media_placeholder(path):
    """Return [image], [audio], [document], or [video] based on file extension or mime."""
    if not path:
        return ""
    path_lower = path.lower()
    if any(ext in path_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', 'image/']):
        return "[image]"
    if any(ext in path_lower for ext in ['.mp3', '.ogg', '.opus', '.m4a', '.wav', 'audio/']):
        return "[audio]"
    if any(ext in path_lower for ext in ['.mp4', '.mov', '.avi', 'video/']):
        return "[video]"
    return "[document]"


def time_window_key(dt):
    """Round datetime down to nearest 30-min window, return HH:MM string."""
    minute = (dt.minute // 30) * 30
    return f"{dt.hour:02d}:{minute:02d}"


def extract_messages(target_date, phone_map):
    """Extract all WhatsApp messages for target_date (WITA).

    Returns dict: { (conversation_label, window_key): [message_dicts] }
    """
    try:
        with open(SESSIONS_INDEX) as f:
            sessions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("ERROR: Cannot read sessions.json", file=sys.stderr)
        return {}

    # Collect all messages grouped by conversation + time window
    grouped = {}

    for session_key, session_meta in sessions.items():
        if 'whatsapp' not in session_key and session_key != 'agent:whatsapp-lite:main':
            continue

        session_id = session_meta.get("sessionId")
        chat_type = session_meta.get("chatType", "direct")
        jsonl_path = os.path.join(SESSIONS_DIR, f"{session_id}.jsonl")

        if not os.path.exists(jsonl_path):
            continue

        is_group = chat_type == "group"
        dm_contact = session_meta.get("lastTo", "")

        with open(jsonl_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if obj.get("type") != "message":
                    continue

                msg = obj["message"]
                role = msg.get("role", "")
                ts_str = obj.get("timestamp", "")

                if not ts_str:
                    continue

                dt = ts_to_wita(ts_str)

                # Filter by target date (WITA)
                if dt.date() != target_date:
                    continue

                # Extract text content
                content = msg.get("content", "")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part["text"]
                            break

                if not text:
                    continue

                window = time_window_key(dt)

                if is_group and role == "user":
                    parsed = parse_group_message_text(text)
                    group_name = parsed["group_subject"] or session_key.split(":")[-1]
                    conv_label = group_name

                    # Process chat history entries — these are the richest source
                    seen_bodies = set()
                    for hist_entry in parsed["chat_history"]:
                        hist_ts_ms = hist_entry.get("timestamp_ms", 0)
                        hist_dt = ms_to_wita(hist_ts_ms)
                        if hist_dt.date() != target_date:
                            continue
                        hist_window = time_window_key(hist_dt)
                        body = hist_entry.get("body", "")
                        sender_raw = hist_entry.get("sender", "")
                        sender = resolve_name(sender_raw, phone_map)
                        dedup_key = f"{sender}:{hist_ts_ms}:{body[:50]}"
                        if dedup_key in seen_bodies:
                            continue
                        seen_bodies.add(dedup_key)

                        key = (conv_label, hist_window)
                        if key not in grouped:
                            grouped[key] = []
                        grouped[key].append({
                            "ts": hist_dt,
                            "ts_ms": hist_ts_ms,
                            "sender": sender,
                            "text": clean_text(body),
                            "is_bot": False,
                        })

                    # Also add the triggering message itself (the one that tagged the bot)
                    sender = resolve_name(parsed["sender_phone"] or parsed["sender_name"], phone_map)
                    actual_text = parsed["actual_text"]
                    media = media_placeholder(parsed["media_path"])
                    display_text = clean_text(actual_text) if actual_text else media

                    if display_text:
                        msg_ts_ms = int(dt.timestamp() * 1000)
                        dedup_key = f"{sender}:{msg_ts_ms}:{display_text[:50]}"
                        # Only add if not already in chat history
                        key = (conv_label, window)
                        if key not in grouped:
                            grouped[key] = []
                        # Check dedup
                        existing = {f"{m['sender']}:{m.get('ts_ms',0)}:{m['text'][:50]}" for m in grouped[key]}
                        if dedup_key not in existing:
                            grouped[key].append({
                                "ts": dt,
                                "ts_ms": msg_ts_ms,
                                "sender": sender,
                                "text": display_text,
                                "is_bot": False,
                            })

                elif is_group and role == "assistant":
                    # Bot reply in group — need to figure out which group this belongs to
                    # Look at previous user message in the same session for context
                    # We attach to the same conv_label by scanning back
                    # Since we process linearly, we track the last group name seen
                    # (handled by the group_name tracking below)
                    pass

                elif not is_group and role == "user":
                    parsed = parse_dm_message_text(text)
                    sender_phone = parsed["sender_phone"] or dm_contact
                    sender = resolve_name(sender_phone, phone_map)
                    actual_text = parsed["actual_text"]
                    media = media_placeholder(parsed["media_path"])
                    display_text = clean_text(actual_text) if actual_text else media

                    if display_text:
                        conv_label = f"DM — {sender}"
                        key = (conv_label, window)
                        if key not in grouped:
                            grouped[key] = []
                        grouped[key].append({
                            "ts": dt,
                            "sender": sender,
                            "text": display_text,
                            "is_bot": False,
                        })

                elif not is_group and role == "assistant":
                    # Bot reply in DM
                    sender = resolve_name(dm_contact, phone_map)
                    reply_text = ""
                    if isinstance(content, str):
                        reply_text = content
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                reply_text = part.get("text", "")
                                break

                    if reply_text:
                        conv_label = f"DM — {sender}"
                        key = (conv_label, window)
                        if key not in grouped:
                            grouped[key] = []
                        grouped[key].append({
                            "ts": dt,
                            "sender": "Bot",
                            "text": clean_text(reply_text),
                            "is_bot": True,
                        })

        # Second pass for group sessions: attach bot replies to correct group
        if is_group:
            last_group = None
            with open(jsonl_path) as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "message":
                        continue
                    msg = obj["message"]
                    role = msg.get("role", "")
                    ts_str = obj.get("timestamp", "")
                    if not ts_str:
                        continue
                    dt = ts_to_wita(ts_str)
                    if dt.date() != target_date:
                        continue

                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text = part["text"]
                                break

                    if role == "user":
                        parsed = parse_group_message_text(text)
                        last_group = parsed["group_subject"] or session_key.split(":")[-1]
                    elif role == "assistant" and last_group:
                        reply_text = text.strip()
                        # Remove textSignature artifacts
                        if reply_text:
                            window = time_window_key(dt)
                            conv_label = last_group
                            key = (conv_label, window)
                            if key not in grouped:
                                grouped[key] = []
                            grouped[key].append({
                                "ts": dt,
                                "sender": "Bot",
                                "text": clean_text(reply_text),
                                "is_bot": True,
                            })

    # Sort messages within each group by timestamp
    for key in grouped:
        grouped[key].sort(key=lambda m: m["ts"])
        # Deduplicate by (sender, text) within same window
        seen = set()
        deduped = []
        for m in grouped[key]:
            dedup = (m["sender"], m["text"])
            if dedup not in seen:
                seen.add(dedup)
                deduped.append(m)
        grouped[key] = deduped

    return grouped


def format_output(grouped):
    """Format grouped messages into markdown log entries.

    Returns list of (header, body) tuples sorted by time.
    """
    entries = []
    for (conv_label, window), messages in sorted(grouped.items(), key=lambda x: x[1][0]["ts"] if x[1] else datetime.min.replace(tzinfo=WITA)):
        if not messages:
            continue
        header = f"### WhatsApp — {conv_label} — {window}"
        lines = []
        for m in messages:
            lines.append(f"- **{m['sender']}:** {m['text']}")
        body = "\n".join(lines)
        entries.append((header, body))
    return entries


def get_existing_headers(memory_path):
    """Read existing memory file and return set of WhatsApp headers already present."""
    headers = set()
    if not os.path.exists(memory_path):
        return headers
    with open(memory_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("### WhatsApp —"):
                headers.add(line)
    return headers


def load_aliases_full():
    """Load full aliases data keyed by slug."""
    try:
        with open(ALIASES_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_employee_match_tokens(employee):
    """Build a set of lowercase match tokens for an employee."""
    tokens = set()
    for alias in employee.get("aliases") or []:
        if alias and len(alias.strip()) >= 2:
            tokens.add(alias.strip().lower())
    phone = employee.get("phone")
    if phone:
        tokens.add(phone)
    wa_name = employee.get("whatsapp_name")
    if wa_name:
        tokens.add(wa_name.strip().lower())
    first = employee.get("first")
    if first and len(first.strip()) >= 2:
        tokens.add(first.strip().lower())
    return tokens


def sender_matches_employee(sender_name, tokens):
    """Check if a resolved sender name matches any employee token."""
    if not sender_name or sender_name in ("Unknown", "Bot"):
        return False
    sender_lower = sender_name.strip().lower()
    return sender_lower in tokens


def find_employee_conversations(grouped, tokens):
    """Find all (conv_label, window) keys where the employee participated as sender.

    Returns set of conv_labels where the employee sent at least one message.
    """
    relevant_convs = set()
    for (conv_label, window), messages in grouped.items():
        for m in messages:
            if sender_matches_employee(m["sender"], tokens):
                relevant_convs.add(conv_label)
                break
    return relevant_convs


def format_employee_log(grouped, relevant_convs, target_date):
    """Format WhatsApp log for a single employee.

    Includes all messages from conversations where the employee participated.
    Returns formatted markdown string, or empty string if no relevant messages.
    """
    # Collect all relevant (conv_label, window) entries
    relevant_entries = []
    for (conv_label, window), messages in grouped.items():
        if conv_label in relevant_convs and messages:
            relevant_entries.append((conv_label, window, messages))

    if not relevant_entries:
        return ""

    # Sort by first message timestamp
    relevant_entries.sort(key=lambda x: x[2][0]["ts"])

    lines = [f"### {target_date} — WhatsApp"]
    for conv_label, window, messages in relevant_entries:
        lines.append("")
        lines.append(f"#### {conv_label} — {window}")
        for m in messages:
            lines.append(f"- **{m['sender']}:** {m['text']}")

    return "\n".join(lines)


def write_employee_logs(grouped, target_date, dry_run=False):
    """Write per-employee WhatsApp logs into team/<slug>.md files."""
    aliases_full = load_aliases_full()
    if not aliases_full:
        print("No aliases loaded, skipping employee logs")
        return

    date_str = str(target_date)
    header_marker = f"### {date_str} — WhatsApp"
    written = 0

    for slug, employee in aliases_full.items():
        tokens = build_employee_match_tokens(employee)
        if not tokens:
            continue

        relevant_convs = find_employee_conversations(grouped, tokens)
        if not relevant_convs:
            continue

        team_path = os.path.join(TEAM_DIR, f"{slug}.md")
        if not os.path.exists(team_path):
            continue

        # Idempotency check — skip if already written
        with open(team_path) as f:
            existing_content = f.read()
        if header_marker in existing_content:
            if dry_run:
                print(f"  [{slug}] already has {header_marker}, skipping")
            continue

        employee_log = format_employee_log(grouped, relevant_convs, target_date)
        if not employee_log:
            continue

        if dry_run:
            print(f"\n--- {slug} ({employee.get('first', slug)}) ---")
            print(employee_log)
            written += 1
            continue

        # Append after "## Activity Log" — find the right insertion point
        # We append at the end of the file (after the last activity log entry)
        with open(team_path, "a") as f:
            f.write("\n\n" + employee_log + "\n")
        written += 1

    action = "Would write" if dry_run else "Wrote"
    print(f"{action} employee WhatsApp logs for {written} employees")


def main():
    parser = argparse.ArgumentParser(description="Extract WhatsApp messages to daily memory files")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: today WITA)")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't write files")
    parser.add_argument("--employee-logs", action="store_true",
                        help="Also write per-employee WhatsApp logs to team/<slug>.md")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(WITA).date()

    phone_map = load_aliases()
    grouped = extract_messages(target_date, phone_map)

    if not grouped:
        print(f"No WhatsApp messages found for {target_date}")
        return

    entries = format_output(grouped)
    if not entries:
        print(f"No entries to write for {target_date}")
        return

    memory_path = os.path.join(MEMORY_DIR, f"{target_date}.md")
    existing_headers = get_existing_headers(memory_path)

    # Filter out already-logged entries
    new_entries = [(h, b) for h, b in entries if h not in existing_headers]

    if not new_entries:
        print(f"All entries already logged for {target_date}")
    else:
        output = "\n\n".join(f"{h}\n{b}" for h, b in new_entries)

        if args.dry_run:
            print(f"--- Dry run for {target_date} ---")
            print(output)
            print(f"--- {len(new_entries)} new entries ({len(entries) - len(new_entries)} already logged) ---")
        else:
            # Append to memory file
            os.makedirs(MEMORY_DIR, exist_ok=True)
            with open(memory_path, "a") as f:
                # Add separator if file has content
                if os.path.exists(memory_path) and os.path.getsize(memory_path) > 0:
                    f.write("\n\n")
                f.write(output)
                f.write("\n")
            print(f"Wrote {len(new_entries)} entries to {memory_path}")

    # Write per-employee logs if requested
    if args.employee_logs:
        write_employee_logs(grouped, target_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
