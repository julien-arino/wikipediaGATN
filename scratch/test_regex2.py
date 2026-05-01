import re
text = '[[Abbotsford]],<ref name="Heintz2025"/> [[Brandon]],<ref>{{cite}}</ref> [[Cranbrook]]'
# Try stripping self-closing first
text1 = re.sub(r'<ref[^>]*/>', '', text, flags=re.IGNORECASE)
text1 = re.sub(r'<ref[^>]*>.*?</ref>', '', text1, flags=re.DOTALL | re.IGNORECASE)

print("Option 1:", text1)

# What if we just do:
text2 = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL | re.IGNORECASE)
print("Option 2:", text2)
