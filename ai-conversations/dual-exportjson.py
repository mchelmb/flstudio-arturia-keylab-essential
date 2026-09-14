import json

def format_for_other_ai(file_path, search_name, output_prefix='ai_ready'):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    # Find the target conversation
    convo = next((c for c in data if search_name.lower() in c.get('name', '').lower()), None)
    
    if not convo:
        print(f"No conversation found matching: '{search_name}'")
        return

    print(f"Found conversation: '{convo.get('name')}'")

    messages = convo.get('chat_messages', [])
    
    markdown_text = []
    api_payload = []

    for msg in messages:
        # Map Claude's roles to standard AI roles (human -> user)
        raw_role = msg.get('sender', '').lower()
        role = "user" if raw_role == "human" else "assistant"
        
        # Extract text content (handles structural variations in attachments/text)
        content = ""
        for item in msg.get('content', []):
            if isinstance(item, dict) and 'text' in item:
                content += item['text'] + "\n"
            elif isinstance(item, str):
                content += item + "\n"
        
        content = content.strip()
        if not content:
            continue

        # Format 1: Text Transcript (Best for pasting directly into an AI chat window)
        display_role = "User" if role == "user" else "Assistant"
        markdown_text.append(f"### {display_role}:\n{content}\n")

        # Format 2: API Object Array (Best for developers or tools like Playground)
        api_payload.append({
            "role": role,
            "content": content
        })

    # Save Markdown Transcript
    md_filename = f"{output_prefix}_transcript.md"
    with open(md_filename, 'w', encoding='utf-8') as f:
        f.write("\n".join(markdown_text))
        
    # Save API JSON Payload
    json_filename = f"{output_prefix}_api_format.json"
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(api_payload, f, indent=2, ensure_ascii=False)

    print(f"Success! Generated:")
    print(f" 1. Text chat log: {md_filename} (Copy/paste this version)")
    print(f" 2. Structured API file: {json_filename} (Use for APIs/Playgrounds)")

if __name__ == "__main__":
    # Configuration
    json_path = 'conversations.json'
    target_name = 'Setting up Claude Code' # Change to your chat title
    
    format_for_other_ai(json_path, target_name)
