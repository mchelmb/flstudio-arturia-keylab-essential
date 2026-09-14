import json
from pathlib import Path

conversations_file = Path('conversations.json')
data = json.loads(conversations_file.read_text())

for c in data:
    if c.get('name') == 'FL Studio VST mapping issues with Keylab controller':
        print(f"=== FL Studio VST Keylab Mapping Conversation ===")
        print(f"UUID: {c['uuid']}")
        print(f"Created: {c.get('created_at')}")
        print(f"Updated: {c.get('updated_at')}")
        print(f"\nTotal messages: {len(c.get('chat_messages', []))}")
        
        for i, msg in enumerate(c['chat_messages']):
            sender = msg.get('sender', 'unknown')
            text = msg.get('text', '')[:300].replace('\n', ' ')
            print(f"\n--- Message {i} ({sender}) ---")
            print(f"Text: {text}...")
        break