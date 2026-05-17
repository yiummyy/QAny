import re

filepath = r'c:\Q\Projects\QAny\QAny产研总结手册.md'

with open(filepath, 'r', encoding='utf-8') as f:
    raw = f.read()

# Target: remove numeric prefixes from ## headings WITHIN section 三
# 三 starts at "# 三、" and ends at "# 四、"
# Only replace ## patterns like "## 1. 核心组件" → "## 核心组件"

replacements = [
    (r'(##) 1\. 核心组件', r'\1 核心组件'),
    (r'(##) 2\. 架构与执行流', r'\1 架构与执行流'),
    (r'(##) 3\. LLM', r'\1 LLM'),
    (r'(##) 4\. Prompt 工程', r'\1 Prompt 工程'),
    (r'(##) 5\. Context 工程', r'\1 Context 工程'),
    (r'(##) 8\. 性能与成本', r'\1 性能与成本'),
    (r'(##) 9\. 可观测性', r'\1 可观测性'),
]

for pattern, replacement in replacements:
    raw = re.sub(pattern, replacement, raw)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(raw)

print(f'Done. Lines: {raw.count(chr(10)) + 1}')
