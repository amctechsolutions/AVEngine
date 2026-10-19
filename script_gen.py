#!/usr/bin/env python3
"""
Private-experiment script drafter on a LOCAL Ollama model (default: scriptwriter = tuned huihui-qwen:7b).
Design: small models fail at whole scripts but do fine on narrow jobs, so FACTS come in, the model only PHRASES them,
one scene per call, each call validated and retried.

  python3 script_gen.py "Termite mounds" --facts facts.txt        # facts.txt: one verified fact per line (recommended)
  python3 script_gen.py "Termite mounds"                          # model brainstorms facts itself (UNRELIABLE, flagged)
Output: drafts/<slug>.json with local_only + needs_fact_check; viral_custom.py renders it only into local_only/.
"""
import argparse, json, re, requests
from pathlib import Path

HERE = Path(__file__).parent
URL = "http://localhost:11434/api/generate"
ABSTRACT = {"concept", "idea", "mystery", "science", "nature", "power", "history", "life", "world", "thing", "wonder", "secret"}


def ask(model, prompt, check, tries=3, temp=0.5):
    """One narrow call, validated; the rejection reason is fed back on retry."""
    fb, last = "", ""
    for _ in range(tries):
        r = requests.post(URL, timeout=300, json={"model": model, "stream": False, "prompt": prompt + fb,
                                                  "options": {"temperature": temp, "num_predict": 120}})
        r.raise_for_status()
        last = r.json()["response"].strip().split("\n")[0].strip().strip('"')
        last = re.sub(r"^(spoken\s+)?(narration|sentence|line|answer|hook|question|statement)\s*:\s*", "", last, flags=re.I).strip().strip('"')
        err = check(last)
        if not err:
            return last, True
        fb = f"\n\nYour last answer was rejected: {err}. Answer again, fixing that."
    return last, False


def words_between(lo, hi, question=None):
    def chk(t):
        n = len(t.split())
        if not lo <= n <= hi:
            return f"it had {n} words, need {lo}-{hi}"
        if question is True and not t.endswith("?"):
            return "it must be a question"
        if question is False and t.endswith("?"):
            return "it must be a statement, not a question"
        return None
    return chk


def visual(model, line):
    def chk(t):
        if "|" not in t:
            return "format must be: nouns | image description"
        q = t.split("|")[0].strip().lower()
        if not 1 <= len(q.split()) <= 3 or set(q.split()) & ABSTRACT:
            return "the search terms must be 1-3 concrete nouns"
        return None
    t, ok = ask(model, f"Narration line: {line}\nGive a stock-footage search of 1-3 CONCRETE nouns, then a | symbol, then one literal sentence "
                       f"describing a photo to illustrate it. Format exactly: nouns | description. No other text.", chk)
    q, _, p = t.partition("|")
    q = " ".join(dict.fromkeys(re.sub(r"[^a-z ]", " ", q.lower()).split()))  # drop _ , punctuation and repeats
    return " ".join(q.split()[:3]), p.strip(), ok


def mark_ai(segs):
    """Strict Pixabay check per scene; scenes with zero exact-match footage get "ai": true (AI illustration instead)."""
    try:
        import time, stock_footage as sf
        if not sf.load_keys().get("pixabay"):
            print("(no Pixabay key: skipping footage check)"); return []
    except Exception as e:
        print(f"(footage check skipped: {e})"); return []
    marked = []
    for i, sg in enumerate(segs, 1):
        try:
            n = len(sf.pixabay_candidates(sg["query"], strict=True)) if sg.get("query") else 0
        except Exception:
            n = 0
        time.sleep(0.8)
        if n == 0:
            sg["ai"] = True; marked.append(i)
        else:
            sg.pop("ai", None)
    return marked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="?")
    ap.add_argument("--mark", metavar="DRAFT.json", help="only (re)run the footage check on an existing draft and mark zero-footage scenes as AI")
    ap.add_argument("--facts", help="file with one verified fact per line")
    ap.add_argument("--model", default="scriptwriter")
    a = ap.parse_args()
    if a.mark:
        f = Path(a.mark); spec = json.loads(f.read_text())
        marked = mark_ai(spec["segments"]); f.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
        print(f"{f.name}: scenes marked as AI (no exact-match footage): {marked or 'none'}"); return
    if not a.topic:
        ap.error("topic required (or use --mark DRAFT.json)")
    m, topic = a.model, a.topic
    facts_given = bool(a.facts)
    if facts_given:
        facts = [l.strip() for l in Path(a.facts).read_text().splitlines() if l.strip()]
    else:
        print("⚠️ no --facts: the model will brainstorm facts from memory (unreliable)")
        raw, _ = ask(m, f"List 6 facts about '{topic}' you are completely certain are true, as one line separated by ' ## '. Hedge anything uncertain.",
                     lambda t: None if t.count("##") >= 4 else "need 6 facts separated by ' ## '")
        facts = [f.strip() for f in raw.split("##") if f.strip()]
    flist = "; ".join(facts)
    segs, flags = [], []
    def not_dup(t):
        e = words_between(9, 16, False)(t)
        if e:
            return e
        tw = set(re.findall(r"[a-z]+", t.lower()))
        for f in facts:
            fw = set(re.findall(r"[a-z]+", f.lower()))
            if len(tw & fw) / max(1, len(tw | fw)) > 0.45:
                return "it repeats one of the facts; make it a teaser that raises curiosity without restating a fact"
        return None
    hook, ok = ask(m, f"Topic: {topic}. Facts: {flist}\nWrite ONE curiosity-raising opening teaser for a 40-second video, 9-16 words, plain spoken English. "
                      f"It must NOT restate any single fact; hint at the surprise only. Use no facts beyond those given. Statement, not a question.", not_dup)
    flags.append(ok); segs.append(("hook", hook))
    for f in facts:
        t, ok = ask(m, f"Rewrite this fact as ONE sentence of spoken narration, 10-20 words, plain English, same meaning. Add no new facts.\nFact: {f}",
                    words_between(10, 20, False))
        flags.append(ok); segs.append(("fact", t))
    close, ok = ask(m, f"Topic: {topic}. Write ONE question (8-14 words) that ends the video by inviting viewers to guess or comment.", words_between(8, 14, True))
    flags.append(ok); segs.append(("close", close))
    out_segs = []
    for kind, text in segs:
        q, p, ok = visual(m, text)
        flags.append(ok)
        out_segs.append({"label": (q.upper() or kind.upper())[:22], "query": q, "text": text, "prompt": p})
    marked = mark_ai(out_segs)
    print(f"scenes marked as AI (no exact-match footage): {marked or 'none'}")
    slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")[:40]
    spec = {"slug": slug, "title": topic, "voice": "adam", "needs_fact_check": True, "local_only": True, "drafted_by": m,
            "facts_supplied": facts_given, "all_checks_passed": all(flags), "claims": facts, "segments": out_segs}
    d = HERE / "drafts"; d.mkdir(exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    print(f"wrote drafts/{slug}.json  ({sum(len(s['text'].split()) for s in out_segs)} words, checks passed: {all(flags)})")
    for i, s in enumerate(out_segs, 1):
        print(f"{i}. [{s['query']}] {s['text']}")


if __name__ == "__main__":
    main()
