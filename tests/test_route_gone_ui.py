"""#110: a chip whose listen is gone must never look like somewhere speech went.

The row keeps showing a session whose listen ended, greyed out and struck
through, so that coming back to the machine shows what happened. Two places
in viewer.js still counted it as a real destination, and both told the person
their words were going somewhere they were not:

  * the number keys, which answer with "now going to X" after setRoute2 has
    already turned the pick down;
  * the poll that notices the destination has ended, which stayed quiet
    because the ended chip was still in the row, and let the fill move with
    nothing said.

The pieces are cut out of viewer.js and run under node with stand-ins for the
page, the same way test_reload_resume.py does it.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER_JS = ROOT / "skills/voice-shell/scripts/viewer.js"

HARNESS = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const assert = (cond, what) => { if (!cond) { console.error(what); process.exit(1); } };

function cut(from, to) {
  const a = source.indexOf(from), b = source.indexOf(to, a);
  if (a < 0 || b < 0) process.exit(2);
  return source.slice(a, b);
}

/* The digit branch of onKey. The slice ends with the two closing braces of
   `if (digit)` and of onKey itself, so a header is all it needs. */
const onKeyBody = 'function onKey(e) {\n'
  + cut('const digit = /^Digit([1-9])$/', "document.addEventListener('keydown', onKey);");

const makeKey = new Function('env', `
  const {chime, say, t} = env;
  const knownListeners = env.knownListeners;
  const setRoute2 = env.setRoute2;
  ${onKeyBody}
  return onKey;
`);

/* The part of loadListeners that decides whether the destination has ended. */
const listenersBody = cut('  const before = knownListeners;',
                          '/* ── Browser recognition settings');

const makeLoad = new Function('env', `
  let knownListeners = env.knownListeners;
  let routeTo = env.routeTo, effectiveTo = '';
  const {t, el, routeNames} = env;
  const before = env.before;
  const relabelEntries = () => {}, paintRoutes = () => {};
  const putJSON = async () => {};
  const d = env.d;
  return (async () => {
    ${listenersBody.replace('const before = knownListeners;', '')
                   .replace(/\}\s*$/, '')}
    return {routeTo, effectiveTo, note: el.note};
  })();
`);
'''


def run(script):
    subprocess.run(["node", "-e", HARNESS + script, str(VIEWER_JS)], check=True)


class GoneChipTest(unittest.TestCase):
    def test_a_number_key_on_a_gone_chip_does_not_claim_it_went_there(self):
        run(r'''
const said = [], chimed = [];
const env = {
  chime: k => chimed.push(k),
  say: m => said.push(m),
  t: (k, v) => k + ':' + (v && v.name || v && v.n || ''),
  knownListeners: [{pid: 11, label: 'alive'}, {pid: 22, label: 'ended', gone: true}],
  setRoute2: to => { throw new Error('setRoute2 called for ' + to); },
};
const onKey = makeKey(env);
onKey({code: 'Digit2', preventDefault(){}});
assert(said.length === 1, 'exactly one line said, got ' + said.length);
assert(said[0].startsWith('listenerGoneHow'), 'says how to start it again: ' + said[0]);
assert(!said.some(s => s.startsWith('voiceRoute:')), 'never acks the move');
assert(chimed.join() === 'err', 'the error chime alone, got ' + chimed.join());
''')

    def test_a_number_key_on_a_live_chip_still_picks_it(self):
        run(r'''
const said = [], picked = [];
const env = {
  chime: () => {},
  say: m => said.push(m),
  t: (k, v) => k + ':' + (v && v.name || ''),
  knownListeners: [{pid: 11, label: 'alive'}, {pid: 22, label: 'ended', gone: true}],
  setRoute2: to => picked.push(to),
};
makeKey(env)({code: 'Digit1', preventDefault(){}});
assert(picked.join() === '11', 'picked the live one, got ' + picked.join());
assert(said[0] === 'voiceRoute:alive', 'acked the move, got ' + said[0]);
''')

    def test_the_destination_ending_is_said_out_loud(self):
        run(r'''
const el = {note: {textContent: '', hidden: true}};
const load = makeLoad({
  t: (k, v) => k + '|' + (v && v.next || ''),
  el, routeNames: new Map(), routeTo: '22',
  before: [{pid: 22, label: 'ended'}],
  knownListeners: [],
  d: {listeners: [{pid: 11, label: 'alive'}, {pid: 22, label: 'ended', gone: true}],
      route: '22', target: '11'},
});
load.then(out => {
  assert(out.routeTo === '', 'the pick is let go, got ' + JSON.stringify(out.routeTo));
  assert(el.note.hidden === false, 'the line is shown');
  assert(el.note.textContent.startsWith('routeGone|'), 'names what happened: ' + el.note.textContent);
  assert(el.note.textContent.endsWith('|alive'), 'moves to the live one: ' + el.note.textContent);
}).catch(e => { console.error(e); process.exit(1); });
''')

    def test_with_every_chip_gone_it_says_so_instead_of_naming_one(self):
        run(r'''
const el = {note: {textContent: '', hidden: true}};
makeLoad({
  t: (k, v) => k + '|' + (v && v.next || ''),
  el, routeNames: new Map(), routeTo: '22',
  before: [{pid: 22, label: 'ended'}],
  knownListeners: [],
  d: {listeners: [{pid: 22, label: 'ended', gone: true}], route: '22', target: ''},
}).then(() => {
  assert(el.note.textContent.startsWith('routeGoneAll'),
         'never names a gone chip as the next one: ' + el.note.textContent);
}).catch(e => { console.error(e); process.exit(1); });
''')

    def test_a_live_destination_is_left_alone(self):
        run(r'''
const el = {note: {textContent: '', hidden: true}};
makeLoad({
  t: k => k, el, routeNames: new Map(), routeTo: '11',
  before: [{pid: 11, label: 'alive'}],
  knownListeners: [],
  d: {listeners: [{pid: 11, label: 'alive'}, {pid: 22, label: 'ended', gone: true}],
      route: '11', target: '11'},
}).then(out => {
  assert(el.note.hidden === true, 'nothing to say');
  assert(out.routeTo === '11', 'the pick stands, got ' + out.routeTo);
}).catch(e => { console.error(e); process.exit(1); });
''')


if __name__ == "__main__":
    unittest.main()
