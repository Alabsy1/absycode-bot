import sys
import re
import os

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove import google.generativeai
content = re.sub(r'import google\.generativeai as genai\n?', '', content)

# 2. Extract GENERIC TEXT HANDLER
pattern_text = r'(# ─────────────────────────────────────────────────────────────\n# GENERIC TEXT HANDLER\n# ─────────────────────────────────────────────────────────────\n@dp\.message\(F\.text & ~F\.text\.startswith\(\'/\'\)\)\nasync def handle_text.*?)(?=\n# ─────────────────────────────────────────────────────────────|\Z)'
match_text = re.search(pattern_text, content, re.DOTALL)
if match_text:
    text_handler_block = match_text.group(1)
    content = content.replace(text_handler_block, '')
    
    # insert before STARTUP
    startup_idx = content.find('# ─────────────────────────────────────────────────────────────\n# STARTUP')
    if startup_idx != -1:
        content = content[:startup_idx] + text_handler_block + '\n\n' + content[startup_idx:]

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed main.py layout')
