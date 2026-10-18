"""Shadow QA: the principal QA engineer that sits either side of every AI call.

Nothing in here calls an AI, reads a key or touches the network. It is plain
Python over rule packs, so it runs inside the request the user already paid
for: a checklist goes out with the prompt, and what the AI still missed comes
back in the same result.
"""
