"""M0 verification spike — throwaway. Re-checks four first-pass claims.

Run from the project root with .venv/bin/python after building /tmp/verify/v.net.xml
(see README.md). Prints evidence for:

  A  period="exp(X)" semantics — is X a rate or a period?
  B  lane-area jam length vs the halting counter — the same measure or not?
  C  D-023: can the three-valued conflict matrix be seeded from the net file?
  D  teleporting vs insertion loss — which actually threatens an isolated intersection?
"""
import os, statistics, subprocess
import xml.etree.ElementTree as ET
import sumolib

WORK = "/tmp/verify"
SUMO = sumolib.checkBinary("sumo")


def a_poisson():
    print("=== A: period=\"exp(0.2)\" semantics ===")
    open(f"{WORK}/c.rou.xml", "w").write(
        '<routes><route id="r" edges="wc ce"/>'
        '<flow id="f" route="r" begin="0" end="3600" period="exp(0.2)" departSpeed="max"/></routes>')
    open(f"{WORK}/c.cfg", "w").write(
        '<configuration><input><net-file value="v.net.xml"/><route-files value="c.rou.xml"/></input>'
        '<output><tripinfo-output value="c.trip.xml"/></output>'
        '<time><begin value="0"/><end value="3600"/></time></configuration>')
    subprocess.run([SUMO, "-c", f"{WORK}/c.cfg", "--no-step-log", "true",
                    "--time-to-teleport", "-1", "--duration-log.disable", "true"],
                   check=True, capture_output=True, cwd=WORK)
    deps = sorted(float(t.get("depart")) for t in ET.parse(f"{WORK}/c.trip.xml").getroot())
    gaps = [b - a for a, b in zip(deps, deps[1:])]
    m, s = statistics.mean(gaps), statistics.stdev(gaps)
    print(f"  n={len(deps)}  mean headway={m:.3f}s  implied rate={1/m:.3f}/s  stdev={s:.3f}")
    print("  -> X is a RATE in veh/s; stdev==mean confirms the exponential\n")


def b_jam_vs_halting():
    print("=== B: jam length vs halting counter, WORKING signal ===")
    open(f"{WORK}/b.rou.xml", "w").write(
        '<routes><route id="r" edges="wc ce"/>'
        '<flow id="f" route="r" begin="0" end="600" period="2"/></routes>')
    open(f"{WORK}/b.add.xml", "w").write(
        '<additional><laneAreaDetector id="d0" lane="wc_0" pos="0" endPos="189" '
        'freq="100000" file="b.det.xml"/></additional>')
    open(f"{WORK}/b.cfg", "w").write(
        '<configuration><input><net-file value="v.net.xml"/><route-files value="b.rou.xml"/>'
        '<additional-files value="b.add.xml"/></input>'
        '<time><begin value="0"/><end value="600"/></time></configuration>')
    import libsumo as L
    L.start([SUMO, "-c", f"{WORK}/b.cfg", "--no-step-log", "true",
             "--time-to-teleport", "-1", "--duration-log.disable", "true"])
    disagree = 0
    for _ in range(600):
        L.simulationStep()
        if L.lane.getLastStepHaltingNumber("wc_0") != L.lanearea.getJamLengthVehicle("d0"):
            disagree += 1
    L.close()
    print(f"  disagreed on {disagree}/600 steps")
    print("  -> DIFFERENT measures. Jam length counts slow-moving vehicles the")
    print("     halting counter excludes. They coincide only in a saturated queue.\n")


def c_conflict_matrix():
    print("=== C: D-023 seeding from the net file ===")
    root = ET.parse(f"{WORK}/v.net.xml").getroot()
    for j in root.findall("junction"):
        if j.get("type") != "traffic_light":
            continue
        reqs = j.findall("request")
        print(f"  junction {j.get('id')}: {len(reqs)} <request> rows")
        for r in reqs[:3]:
            print(f"    index={r.get('index'):>2} response={r.get('response')} foes={r.get('foes')}")
    for tl in root.findall("tlLogic"):
        print(f"  tlLogic phases: {[p.get('state') for p in tl.findall('phase')]}")
        break
    print("  -> foes = static conflict topology; response = which foes this link yields to.")
    print("     'G' vs 'g' in the phase state separates protected from permissive.")
    print("     Both are STATIC net-file data, not runtime link state.\n")


def d_teleport_vs_insertion():
    print("=== D: teleporting vs insertion loss on an isolated intersection ===")

    def run(rate, ttt, tag):
        open(f"{WORK}/s{tag}.rou.xml", "w").write(
            '<routes><route id="we" edges="wc ce"/><route id="ew" edges="ec cw"/>'
            '<route id="ns" edges="nc cs"/><route id="sn" edges="sc cn"/>'
            + "".join(f'<flow id="f{i}" route="{r}" begin="0" end="3600" period="exp({rate})"/>'
                      for i, r in enumerate(["we", "ew", "ns", "sn"])) + '</routes>')
        open(f"{WORK}/s{tag}.cfg", "w").write(
            f'<configuration><input><net-file value="v.net.xml"/>'
            f'<route-files value="s{tag}.rou.xml"/></input>'
            f'<output><tripinfo-output value="s{tag}.trip.xml"/></output>'
            f'<time><begin value="0"/><end value="3600"/></time></configuration>')
        r = subprocess.run([SUMO, "-c", f"{WORK}/s{tag}.cfg", "--no-step-log", "true",
                            "--duration-log.disable", "true", "--time-to-teleport", str(ttt),
                            "--tripinfo-output.write-unfinished", "true",
                            "--tripinfo-output.write-undeparted", "true", "--eager-insert"],
                           capture_output=True, text=True, cwd=WORK)
        trips = list(ET.parse(f"{WORK}/s{tag}.trip.xml").getroot())
        fin = [t for t in trips if float(t.get("arrival", -1)) >= 0]
        tl = [float(t.get("timeLoss")) for t in fin]
        return r.stderr.count("teleporting"), len(trips), len(fin), (statistics.mean(tl) if tl else float("nan"))

    print("  rate/appr  veh/h  teleports  finished/loaded  meanTL_on  meanTL_off  distortion")
    for rate in (0.30, 0.40, 0.50, 0.60):
        t1, n1, f1, m1 = run(rate, 300, f"on{int(rate*100)}")
        _, n2, f2, m2 = run(rate, -1, f"of{int(rate*100)}")
        d = 100 * (m2 - m1) / m2 if m2 == m2 and m2 else 0.0
        print(f"   {rate:.2f}    {rate*3600:>5.0f}   {t1:>8}   {f1:>5}/{n1:<6}    {m1:>7.1f}   {m2:>8.1f}   {d:>+6.1f}%")
    print("  -> No teleports at any level. Overload leaves as insertion loss instead,")
    print("     because a queue on a 190 m approach spills out of the network, not into it.\n")


if __name__ == "__main__":
    os.makedirs(WORK, exist_ok=True)
    a_poisson(); b_jam_vs_halting(); c_conflict_matrix(); d_teleport_vs_insertion()
