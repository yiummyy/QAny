import re
import shutil

filepath = r'c:\Q\Projects\QAny\QAny产研总结手册.md'
backup = filepath + '.bak'

shutil.copy(backup, filepath)

with open(filepath, 'r', encoding='utf-8') as f:
    raw = f.read()

# ============================================================
# Step 1: Capture three-10 content and remove it from three
# ============================================================
# No *** before ## 10, but *** after it before # 四

pat1 = re.compile(
    r'(\n## 10\. 评估、部署与运维.*?)'
    r'(\n\*\*\*\n\n# 四、RAG 实现细节)',
    re.DOTALL
)
m1 = pat1.search(raw)
if not m1:
    print('Step 1 FAILED')
    exit(1)

blk_10 = m1.group(1)  # "\n## 10. ..."  all content
blk_4  = m1.group(2)  # "\n***\n\n# 四、..."

body = re.sub(r'\n## 10\. 评估、部署与运维\s*', '', blk_10, count=1, flags=re.DOTALL)
raw = raw.replace(blk_10 + blk_4, blk_4)
print('Step 1 OK')

# ============================================================
# Step 2: Replace old 六 content with three-10 content
# ============================================================

pat2 = re.compile(
    r'(# 六、评测体系.*?)'
    r'(\n\*\*\*\n\n# 七、成本管理)',
    re.DOTALL
)
m2 = pat2.search(raw)
if not m2:
    print('Step 2 FAILED')
    exit(1)

old_six = m2.group(1)
mk7 = m2.group(2)
new_six = '# 六、评测体系\n\n' + body.lstrip()
raw = raw.replace(old_six + mk7, new_six + mk7)
print('Step 2 OK')

# ============================================================
# Step 3: Merge ## 6. 安全 + ## 7. 可靠 -> 安全与可靠性
# ============================================================
# All ## sections within three are separated by blank lines, no ***

pat3 = re.compile(
    r'(## 6\. 安全与可控性\n\n.*?)'
    r'(\n\n## 7\. 可靠性与弹性\n\n)'
    r'(.*?)'
    r'(\n\n## 8\. 性能与成本)',
    re.DOTALL
)
m3 = pat3.search(raw)
if not m3:
    print('Step 3 FAILED')
    exit(1)

s6_raw = m3.group(1)
s7_sep = m3.group(2)
s7_raw = m3.group(3)
s8_raw = m3.group(4)

s6_body = re.sub(r'^## 6\. 安全与可控性\n\n', '', s6_raw, count=1, flags=re.DOTALL)
s7_body = re.sub(r'^## 7\. 可靠性与弹性\n\n', '', s7_raw, count=1, flags=re.DOTALL)

merged = (
    '## 安全与可靠性\n\n'
    + s6_body.strip()
    + '\n\n***\n\n'
    + s7_body.strip()
)

old_blob = s6_raw + s7_sep + s7_raw
raw = raw.replace(old_blob + s8_raw, merged + s8_raw)
print('Step 3 OK')

# Write
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(raw)

lines = raw.count('\n') + 1
print(f'ALL DONE. Lines: {lines}')
