import re

file_path = "ui/index.html"
with open(file_path, "r", encoding="utf-8") as f:
    js_code = f.read()

# Find all document.getElementById('...')
ids = set(re.findall(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)", js_code))
print("IDs referenced in JS:")
print(sorted(list(ids)))

# Find any querySelector referencing IDs or classes
selectors = set(re.findall(r"querySelector\(['\"]([^'\"]+)['\"]\)", js_code))
print("\nSelectors referenced in JS:")
print(sorted(list(selectors)))
