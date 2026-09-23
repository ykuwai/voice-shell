import io

js = 'skills/voice-shell/scripts/viewer.js'
s = io.open(js, encoding='utf-8', newline=None).read()

start = s.index('// Full-width Latin letters and digits')
end = s.index("/* The one string both writers to el.stream agree on:")
block = s[start:end]
assert block.endswith('\n\n'), repr(block[-20:])
s = s[:start] + s[end:]

anchor = "const TAIL_IDS = ['cancel_tail', 'hold_tail', 'mute'];"
assert s.count(anchor) == 1
s = s.replace(anchor, block + anchor)
io.open(js, 'w', encoding='utf-8', newline='\r\n').write(s)


def patch(path, pairs):
    t = io.open(path, encoding='utf-8', newline=None).read()
    for old, new in pairs:
        assert t.count(old) == 1, (path, repr(old[:70]), t.count(old))
        t = t.replace(old, new)
    io.open(path, 'w', encoding='utf-8', newline='\r\n').write(t)


# The two harnesses slice from the tail tables down; foldChars now leans on
# toHalfWidth, which sits just above them.
patch('tests/test_command_switch_off.py', [
    ('''const start = source.indexOf("const TAIL_IDS = ");
const end = source.indexOf("function endsWithTailCmd", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('words', 'off', `''',
     '''const start = source.indexOf("// Full-width Latin letters and digits");
const end = source.indexOf("function endsWithTailCmd", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('words', 'off', `'''),
    ('''const start = source.indexOf("const TAIL_IDS = ");
const end = source.indexOf("function endsWithTailCmd", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('words', 'off', 'user', `''',
     '''const start = source.indexOf("// Full-width Latin letters and digits");
const end = source.indexOf("function endsWithTailCmd", start);
if (start < 0 || end < 0) process.exit(2);
const body = source.slice(start, end);
const make = new Function('words', 'off', 'user', `'''),
])

patch('tests/test_halfwidth.py', [
    ("source.indexOf('function browserStreamText()', start)",
     "source.indexOf('const TAIL_IDS = ', start)"),
])
print("ok")
