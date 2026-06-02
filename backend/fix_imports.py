import os

backend_dir = os.path.dirname(os.path.abspath(__file__))

for root, _, files in os.walk(backend_dir):
    for file in files:
        if file.endswith(".py") and file != "fix_imports.py":
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'from backend.' in content or 'import backend.' in content:
                new_content = content.replace('from backend.', 'from ').replace('import backend.', 'import ')
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Fixed imports in {filepath}")
