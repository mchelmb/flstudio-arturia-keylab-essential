import json
from pathlib import Path

CONVERSATIONS_FILE = Path('conversations.json')
OUTPUT_PREFIX = 'keylab_nav'

data = json.loads(CONVERSATIONS_FILE.read_text(encoding='utf-8'))

target_uuid = '4c30f886-8899-4eea-9ca6-d45c89c71111'
convo = next((c for c in data if c.get('uuid') == target_uuid), None)

if not convo:
    raise SystemExit(f"No conversation found with UUID {target_uuid}")

messages = convo.get('chat_messages', [])

markdown_lines = []
api_payload = []

for msg in messages:
    raw_role = msg.get('sender', '').lower()
    role = "user" if raw_role == "human" else "assistant"

    content = msg.get('text', '')
    if not content:
        for item in msg.get('content', []):
            if isinstance(item, dict) and 'text' in item:
                content += item['text'] + "\n"
            elif isinstance(item, str):
                content += item + "\n"

    content = content.strip()
    if not content:
        continue

    display_role = "User" if role == "user" else "Assistant"
    markdown_lines.append(f"### {display_role}:\n{content}\n")

    api_payload.append({"role": role, "content": content})

md_filename = f"{OUTPUT_PREFIX}_transcript.md"
Path(md_filename).write_text("\n".join(markdown_lines), encoding='utf-8')

json_filename = f"{OUTPUT_PREFIX}_api_format.json"
Path(json_filename).write_text(json.dumps(api_payload, indent=2, ensure_ascii=False), encoding='utf-8')

print(f"Extracted: {convo.get('name')}")
print(f"UUID: {convo.get('uuid')}")
print(f"Messages processed: {len(messages)}")
print(f"Generated: {md_filename}, {json_filename}")