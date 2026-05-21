import sys

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

bad_str = r"""f"JSON format: {{\\"mode\\":\\"total/full\\",\\"store\\":\\"str\\",\\"date\\":\\"YYYY-MM-DD\\","
                          f"\\"total\\":float,\\"items\\":[{{\\"name\\":\\"str\\",\\"price\\":float,\\"qty\\":int}}]}}\\n\""""

good_str = """f'JSON format: {{"mode":"total/full","store":"str","date":"YYYY-MM-DD",'
                          f'"total":float,"items":[{{"name":"str","price":float,"qty":int}}]}}\\n'"""

# The above might be tricky with exactly matching all backslashes.
# Let's just use regex on the lines.
import re

content = re.sub(
    r'f"JSON format: \{\{\\\\"mode\\\\":\\\\"total/full\\\\",.*?"qty\\\\":int\}\]\}\}\\\\n"',
    good_str,
    content,
    flags=re.DOTALL
)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fix applied")
