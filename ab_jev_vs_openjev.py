"""A/B Jev (OpenRouter) vs openJev local 20ms - 5 tasks"""
import os, time, pathlib, re, json
import sys
sys.path.insert(0, "C:/Users/ADMIN/hermes-jev-skills")
# Jev setup
env_text = pathlib.Path("C:/Users/ADMIN/jev-spike/.env").read_text(encoding="utf-8")
m=re.search(r'^JEV_KEY\s*=\s*(.+)$', env_text, re.M); key=m.group(1).strip().strip('"').strip("'") if m else ""
m2=re.search(r'^JEV_URL\s*=\s*(.+)$', env_text, re.M); url=m2.group(1).strip().strip('"').strip("'") if m2 else ""
os.environ["JEV_URL"]=url
os.environ["TYPESAFE_API_KEY"]=key
os.environ["TYPESAFE_MODEL"]="typesafe/jev-1.13"
print(f"Jev via {url[:40]} key len {len(key)}")

# openJev setup
import sys
sys.path.insert(0, "C:/Users/ADMIN/openJev-verdict-2.0")
from core.engine_encoder import DecisionEngine
from core.primitives import Choice, Option, Noul
from core.calibration import TemperatureCalibrator
model_path="C:/Users/ADMIN/openJev-verdict-2.0/hf_rlcd"
cal_path=pathlib.Path(model_path)/"calibrator.json"
cal=TemperatureCalibrator.load(str(cal_path)) if cal_path.exists() else TemperatureCalibrator(initial_temperature=1.0)
print("Loading openJev...")
t0=time.time()
engine=DecisionEngine(model_name_or_path=model_path, calibrator=cal, device="cpu")
print(f"openJev loaded {(time.time()-t0)*1000:.0f} ms (warmup)")

# Warmup openJev
from core.primitives import Choice, Option
ctx="warmup"
q=Choice(id="q", question="Pick", options=(Option(id="a", description="a"), Option(id="b", description="b")))
engine.evaluate(ctx, [q])

# Jev helpers
from jevkit.client import ask, choice as jev_choice, noul as jev_noul

def test_case(name, ctx, jev_questions, open_queries, expect):
    print(f"\n=== {name} ===")
    print(f"Context: {ctx[:80]}...")
    # Jev
    t0=time.time()
    try:
        res_jev = ask(ctx, jev_questions, timeout=8)
        dt_jev = res_jev['latency_ms']
        ans_jev = res_jev['answers']
        # get first answer choice
        first_key = list(ans_jev.keys())[0]
        pick_jev = ans_jev[first_key].get('choice') or ans_jev[first_key].get('noul')
        conf_jev = ans_jev[first_key].get('confidence', 0)
        print(f" Jev: {dt_jev} ms | pick {pick_jev} conf {conf_jev:.2f} | expect {expect} -> {'✅' if str(pick_jev)==str(expect) else '❌'}")
    except Exception as e:
        print(f" Jev error: {e}")
        dt_jev=None; pick_jev=None
    # openJev
    t0=time.time()
    try:
        res_open = engine.evaluate(ctx, open_queries)
        dt_open = res_open.total_latency_ms
        # assume first result
        r=res_open.results[0]
        if r.kind=="choice":
            pick_open=r.selected_id
            conf_open=r.selected_probability
        elif r.kind=="noul":
            pick_open=r.selected_outcome
            conf_open=1-r.p_insufficient_evidence if r.p_true_given_sufficient_evidence else 0
        else:
            pick_open=r.selected_id
            conf_open=0
        print(f" openJev: {dt_open:.0f} ms | pick {pick_open} conf {conf_open:.2f} | expect {expect} -> {'✅' if str(pick_open)==str(expect) else '❌'}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f" openJev error: {e}")
        dt_open=None; pick_open=None
    if dt_jev and dt_open:
        print(f"  Speedup: {dt_jev/dt_open:.1f}x (Jev {dt_jev}ms vs openJev {dt_open:.0f}ms)")

# 1. Memory-like: choose relevant passage (simplified)
test_case(
    "1. Memory relevance (HPG)",
    "Find HPG Q2 2026 revenue. Passages: rel0 HPG revenue 20000B, irr0 recipe pho",
    {"pick": jev_choice("Which passage answers the query?", {"rel0":"HPG Q2 2026 revenue 20000B","irr0":"Recipe for pho"})},
    [Choice(id="pick", question="Which passage answers the query?", options=(Option(id="rel0", description="HPG Q2 2026 revenue 20000B"), Option(id="irr0", description="Recipe for pho")))],
    "rel0"
)

# 2. Skill-select like
test_case(
    "2. Skill-select (BCTC)",
    "Phân tích báo cáo tài chính HPG Q2 2026 và so sánh với ngành thép",
    {"pick": jev_choice("Which skill is the specialised procedure?", {"vn-market-data":"vn-market-data: Fetch market data","other":"other: generic"})},
    [Choice(id="pick", question="Which skill is the specialised procedure?", options=(Option(id="vn-market-data", description="vn-market-data: Fetch market data"), Option(id="other", description="other: generic")))],
    "vn-market-data"
)

# 3. Triage (noul)
test_case(
    "3. Triage urgent payment",
    "Urgent: Production payment failure, customer blocked. Payment gateway down, money at risk.",
    {"urgent": jev_noul("This requires immediate action right now")},
    [Noul(id="urgent", proposition="This requires immediate action right now", semantics="conditional_on_sufficient_evidence_v2")],
    "true"
)

# 4. Browser choose (Appearance)
test_case(
    "4. Browser choose Appearance",
    "Goal: Open Settings and select Appearance. Regions: Appearance, General",
    {"pick": jev_choice("Pick the next action", {"select-appearance":"Click Appearance","select-general":"Click General","reobserve":"Take a fresh observation"})},
    [Choice(id="pick", question="Pick the next action", options=(Option(id="select-appearance", description="Click Appearance"), Option(id="select-general", description="Click General"), Option(id="reobserve", description="Take a fresh observation")))],
    "select-appearance"
)

# 5. Flights-like (One way)
test_case(
    "5. Flights One way",
    "Goal: Find one-way flights Zurich to London. Ticket type is Round trip, need One way",
    {"pick": jev_choice("Pick the next action", {"One way":"One way","Round trip":"Round trip","Multi-city":"Multi-city"})},
    [Choice(id="pick", question="Pick the next action", options=(Option(id="One way", description="One way"), Option(id="Round trip", description="Round trip"), Option(id="Multi-city", description="Multi-city")))],
    "One way"
)
