import re
text = '[[Abbotsford]],<ref name="Heintz2025"/> [[Brandon]],<ref>{{cite}}</ref> [[Cranbrook]]'

# Option 2:
text2 = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL | re.IGNORECASE)
print("Option 2:", text2)

# Option 3 (reversed):
text3 = re.sub(r'<ref[^>]*>.*?</ref>|<ref[^>]*/>', '', text, flags=re.DOTALL | re.IGNORECASE)
print("Option 3:", text3)
