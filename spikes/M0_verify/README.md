# M0 verification spike

Re-checks four claims made by the first pass of T0.2, T0.3, T0.4 and T0.5, each of which
was either unverified, measured in an invalid regime, or wrong. Findings are folded into
the corresponding `research/M0_*.md` documents and into the decision register.

Build the probe network (a four-way with two lanes per approach and netconvert-inferred
connections, TLS and turn lanes — it has a **permissive** left, which the original
reference scenario did not):

    .venv/bin/python -c "import subprocess,sumolib; subprocess.run([sumolib.checkBinary('netconvert'),'-n','spikes/M0_verify/v.nod.xml','-e','spikes/M0_verify/v.edg.xml','-o','/tmp/verify/v.net.xml','--tls.guess','true','--no-turnarounds','true'],check=True)"

Then run `verify.py`. It is throwaway spike code per `08_AGENT_HANDOFF_PROTOCOL.md` §2.1.
