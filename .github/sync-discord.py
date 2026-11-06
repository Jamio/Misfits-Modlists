import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import urllib.error
from decimal import Decimal
from http.client import HTTPException
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from string import Template
from uuid import uuid4

pack, mode = sys.argv[1:]
if mode not in {"preview", "post", "update"} or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", pack):
    raise SystemExit("Use a lowercase modpack folder name with letters, numbers and hyphens.")
if mode == "post" and (pack == "ww2" or os.environ.get("GITHUB_REF") != "refs/heads/main"):
    raise SystemExit("New modpacks can only be posted from main.")

if pack == "ww2":
    preset = Path("Misfits WW2.html")
    banner = Path(".github/ww2-banner.png")
    state = Path(".github/discord-ww2-message-id.txt")
else:
    folder = Path("modpacks") / pack
    presets = list(folder.glob("*.html"))
    if len(presets) != 1:
        raise SystemExit(f"{folder} must contain exactly one HTML preset.")
    preset, = presets
    banner = folder / "banner.png"
    state = folder / "discord-message-id.txt"

if not preset.is_file() or not banner.is_file():
    raise SystemExit("The modpack needs an HTML preset and a PNG banner.")
if any(character in preset.name for character in '"\\\r\n'):
    raise SystemExit("Use an HTML filename without quotes, backslashes or line breaks.")
if mode == "post" and state.exists():
    raise SystemExit("This pack already has a message or an unfinished posting attempt. Check its saved ID.")

message_id = state.read_text(encoding="utf-8").strip() if state.is_file() else ""
if mode == "update" and not re.fullmatch(r"[0-9]{17,20}", message_id):
    raise SystemExit("Missing or invalid saved Discord message ID.")

class DlcParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = []
        self.in_dlc = False
        self.name_parts = None

    def handle_starttag(self, tag, attrs):
        kind = dict(attrs).get("data-type")
        if tag == "tr":
            self.in_dlc = kind == "DlcContainer"
        elif tag == "td" and self.in_dlc and kind == "DisplayName":
            self.name_parts = []

    def handle_endtag(self, tag):
        if tag == "td" and self.name_parts is not None:
            name = " ".join("".join(self.name_parts).split())
            if name and name not in self.names:
                self.names.append(name)
            self.name_parts = None
        elif tag == "tr":
            self.in_dlc = False

    def handle_data(self, data):
        if self.name_parts is not None:
            self.name_parts.append(data)

preset_bytes = preset.read_bytes()
html = preset_bytes.decode("utf-8-sig")
parser = DlcParser()
parser.feed(html)
parser.close()

ids = set(re.findall(
    r"steamcommunity\.com/sharedfiles/filedetails/"
    r"\?(?:[^\"'<>\s]*?&amp;)?id=(\d+)", html
))
if not ids:
    raise SystemExit("No Workshop IDs found. Check the preset export.")

# This map is the shared, maintainer-reviewed list of compatibility links.
links = json.loads(Path(".github/discord-dlc-compatibility.json").read_text(encoding="utf-8"))
if not isinstance(links, dict) or any(
    not isinstance(url, str) or not re.fullmatch(
        r"https://steamcommunity\.com/sharedfiles/filedetails/\?id=[1-9][0-9]*", url
    )
    for url in links.values()
):
    raise SystemExit("Compatibility links must use canonical Steam Workshop URLs.")

def escape_name(name):
    return re.sub(r"([\\\x60*_{}\[\]()<>#+.!|~])", r"\\\1", name)

dlc_lines = [
    f"- {escape_name(name)}" + (
        f" ([Compatibility data for non-owners]({links[name]}))" if name in links else ""
    )
    for name in parser.names
]
def estimate_size(item_ids):
    endpoint = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    ordered_ids = sorted(item_ids)
    sizes = {}
    details_by_id = {}
    for offset in range(0, len(ordered_ids), 50):
        batch = ordered_ids[offset:offset + 50]
        fields = {"itemcount": len(batch)}
        fields.update({f"publishedfileids[{index}]": item for index, item in enumerate(batch)})
        request = urllib.request.Request(endpoint, data=urllib.parse.urlencode(fields).encode("ascii"))
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            print(f"Steam batch lookup returned HTTP {error.code}.")
            break
        except (OSError, HTTPException, ValueError):
            print("Steam batch lookup failed or returned invalid JSON.")
            break
        data = payload.get("response", {}) if isinstance(payload, dict) else {}
        rows = data.get("publishedfiledetails", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = str(row.get("publishedfileid", ""))
            if item not in batch:
                continue
            result = row.get("result")
            size = str(row.get("file_size", ""))
            if result == 1 and re.fullmatch(r"[1-9][0-9]{0,19}", size):
                sizes[item] = int(size)
            elif isinstance(result, int) and result != 1:
                details_by_id[item] = f"Steam result {result}"
            else:
                details_by_id[item] = "no positive file size"

    print(f"Workshop size lookup: {len(sizes)}/{len(item_ids)} sizes read.")
    for item in sorted(item_ids - sizes.keys()):
        reason = details_by_id.get(item, "no item details returned")
        print(f"Workshop size unavailable for item {item}: {reason}.")
    if len(sizes) != len(item_ids) and mode != "preview":
        raise SystemExit("Workshop size lookup incomplete. Existing Discord message was left unchanged.")
    if not sizes:
        return "unavailable (could not read Workshop sizes)"
    total_gb = Decimal(sum(sizes.values())) / 10**9
    amount = f"~{total_gb:,.1f} GB" if total_gb >= Decimal("0.1") else "<0.1 GB"
    if len(sizes) != len(item_ids):
        return f"{amount} subtotal ({len(sizes)}/{len(item_ids)} mods checked)"
    return amount

template = Template(Path(".github/discord-modlist-message.md").read_text(encoding="utf-8"))
try:
    description = template.substitute(
        modlist_name=preset.stem,
        mod_count=len(ids),
        workshop_size=estimate_size(ids),
        updated_date=datetime.now(timezone.utc).strftime("%d %B %Y"),
        dlc_list="\n".join(dlc_lines) or "None listed in the preset.",
    ).strip()
except (ValueError, KeyError):
    raise SystemExit("Invalid placeholder in the Discord message template.") from None
if not 0 < len(description.encode("utf-16-le")) // 2 <= 4096:
    raise SystemExit("The Discord container text must contain 1–4096 characters.")

title, _, details = description.partition("\n")
if not details.strip():
    raise SystemExit("The Discord template needs a heading followed by message details.")
banner_bytes = banner.read_bytes()
if not banner_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
    raise SystemExit("The banner must be a PNG image.")

message = {
    "content": None,
    "embeds": None,
    "flags": 1 << 15,
    "components": [{
        "type": 17,
        "accent_color": 0xC0392B,
        "components": [
            {"type": 10, "content": title},
            {"type": 12, "items": [{
                "media": {"url": f"attachment://{banner.name}"},
                "description": f"{preset.stem} modpack banner",
            }]},
            {"type": 10, "content": details.strip()},
            {"type": 13, "file": {"url": f"attachment://{preset.name}"}},
        ],
    }],
    "allowed_mentions": {"parse": []},
    "attachments": [
        {"id": 0, "filename": preset.name},
        {"id": 1, "filename": banner.name},
    ],
}
if mode == "post":
    del message["content"], message["embeds"]

if mode == "preview":
    print(json.dumps(message, ensure_ascii=False, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        repo = os.environ["GITHUB_REPOSITORY"]
        sha = os.environ["GITHUB_SHA"]
        image = f"https://raw.githubusercontent.com/{repo}/{sha}/{urllib.parse.quote(banner.as_posix())}"
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"{title}\n\n![Modpack banner]({image})\n\n{details.strip()}\n\nAttachment: `{preset.name}`\n")
    raise SystemExit(0)

webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip().rstrip("/")
if not re.fullmatch(
    r"https://(?:discord\.com|discordapp\.com)/api/(?:v[0-9]+/)?webhooks/[0-9]+/[A-Za-z0-9_-]+",
    webhook,
):
    raise SystemExit("DISCORD_WEBHOOK_URL is missing or invalid.")
endpoint = (
    f"{webhook}?wait=true&with_components=true" if mode == "post"
    else f"{webhook}/messages/{message_id}?with_components=true"
)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

boundary = uuid4().hex
body = bytearray()

def part(name, content, filename=None, content_type=None):
    body.extend(f"--{boundary}\r\n".encode())
    disposition = f'form-data; name="{name}"'
    if filename:
        disposition += f'; filename="{filename}"'
    body.extend(
        f"Content-Disposition: {disposition}\r\n".encode()
    )
    if content_type:
        body.extend(
            f"Content-Type: {content_type}\r\n".encode()
        )
    body.extend(b"\r\n")
    body.extend(content)
    body.extend(b"\r\n")

part(
    "payload_json",
    json.dumps(message).encode(),
    content_type="application/json"
)
part(
    "files[0]",
    preset_bytes,
    filename=preset.name,
    content_type="application/octet-stream"
)
part("files[1]", banner_bytes, filename=banner.name, content_type="image/png")
body.extend(f"--{boundary}--\r\n".encode())

request = urllib.request.Request(
    endpoint,
    data=bytes(body),
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Misfits-Modlist-Sync/1.0"
    },
    method="POST" if mode == "post" else "PATCH"
)

def save_state(value, commit_message, rebase=False):
    state.write_text(value + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", str(state)], check=True)
    subprocess.run([
        "git", "-c", "user.name=github-actions[bot]", "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", commit_message,
    ], check=True)
    if rebase:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)

if mode == "post":
    # Reserve the pack before Discord can receive a POST. A failed or interrupted
    # run leaves this marker in GitHub so that retries cannot create duplicates.
    save_state("pending", f"Reserve Discord message for {pack}")

try:
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=60) as response:
        result = json.load(response)
except urllib.error.HTTPError as error:
    raise SystemExit(f"Discord rejected the request (HTTP {error.code}). Check the webhook and saved ID.") from None
except (OSError, ValueError):
    raise SystemExit("Could not confirm the Discord request. Check the channel before retrying.") from None

returned_id = result.get("id", "") if isinstance(result, dict) else ""
if not isinstance(returned_id, str) or not re.fullmatch(r"[0-9]{17,20}", returned_id):
    raise SystemExit("Discord returned an invalid message ID. Check the channel.")
if mode == "post":
    print(f"Discord created message {returned_id} for {pack}. Saving its ID.", flush=True)
    save_state(returned_id, f"Save Discord message ID for {pack}", rebase=True)
elif returned_id != message_id:
    raise SystemExit("Discord returned an unexpected message ID.")
if not result.get("flags", 0) & (1 << 15) or not result.get("components"):
    raise SystemExit("Discord did not confirm the container layout.")
print(f"Discord message synced for {pack}. Workshop mods: {len(ids)}")
