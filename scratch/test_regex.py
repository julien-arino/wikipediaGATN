import re

dests_raw = '[[Abbotsford]],<ref name="Heintz2025"/> [[Brandon]],<ref>{{cite}}</ref> [[Cranbrook]]'
cleaned = re.sub(r'<ref.*?</ref>', '', dests_raw, flags=re.DOTALL)
print("Cleaned:", cleaned)
