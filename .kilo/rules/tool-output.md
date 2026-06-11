# Tool Output Protocol

Do not paste long raw terminal output into chat.
All scripts must be run as:
`env PYTHONPATH=src:scripts .venv/bin/python3 <script> <args> > /tmp/sN.txt 2>&1`
Then inspect with:
`tail -20 /tmp/sN.txt`
If output exceeds 10 lines in chat, the response failed the protocol.
