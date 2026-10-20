#!/usr/bin/env python3
"""Tic-tac-toe for the profile README, driven by GitHub issues.

Visitors click a square on the README board. That opens a prefilled issue titled
"ttt|move|<0-8>". The workflow runs this script, which plays the visitor's move,
plays the bot's reply, rewrites the board in README.md and writes comment.md.

Usage:
  TITLE="ttt|move|4" USER_LOGIN="octocat" python .github/scripts/game.py
  python .github/scripts/game.py render      # only re-render the README board
"""
import json
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / ".github" / "game" / "state.json"
README_PATH = ROOT / "README.md"
COMMENT_PATH = ROOT / "comment.md"

REPO = os.environ.get("REPO", "Shreyas652/Shreyas652")
START, END = "<!--TTT-START-->", "<!--TTT-END-->"

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
SYMBOL = {"": "⬜", "X": "❌", "O": "⭕"}
MOVE_RE = re.compile(r"^ttt\|move\|([0-8])$")
NEW_RE = re.compile(r"^ttt\|new$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
FRESH_MSG = "Your move. You are ❌ and I am ⭕."


def load():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def outcome(board):
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return "draw" if all(board) else None


def bot_move(board):
    """Win if possible, block if needed, otherwise usually take a strong square.

    The 25% random move keeps the bot beatable, so visitors can actually win.
    """
    empty = [i for i, c in enumerate(board) if not c]
    for mark in ("O", "X"):
        for i in empty:
            trial = board[:]
            trial[i] = mark
            if outcome(trial) == mark:
                return i
    if random.random() < 0.75:
        for i in (4, 0, 2, 6, 8):
            if i in empty:
                return i
    return random.choice(empty)


def issue_link(title):
    body = quote("Just click 'Submit new issue'. A bot plays the move and closes this issue in about 30 seconds.")
    return f"https://github.com/{REPO}/issues/new?title={quote(title, safe='')}&body={body}"


def render(state):
    rows = []
    for r in range(3):
        cells = []
        for c in range(3):
            i = r * 3 + c
            sym = SYMBOL[state["board"][i]]
            if not state["board"][i] and not state["over"]:
                href = issue_link(f"ttt|move|{i}")
                cells.append(f'<td align="center" width="70"><a href="{href}">{sym}</a></td>')
            else:
                cells.append(f'<td align="center" width="70">{sym}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    stats = state["stats"]
    recent = ", ".join(f"[@{u}](https://github.com/{u})" for u in state["recent"]) or "nobody yet"
    again = ""
    if state["over"]:
        again = f'\n\n<a href="{issue_link("ttt|new")}"><b>▶ Play again</b></a>'

    return (
        '<div align="center">\n\n'
        f"**{state['message']}**\n\n"
        f"<table>{''.join(rows)}</table>"
        f"{again}\n\n"
        f"🧑 You: **{stats['you']}** &nbsp;|&nbsp; 🤖 Bot: **{stats['bot']}** &nbsp;|&nbsp; 🤝 Draws: **{stats['draw']}**\n\n"
        f"<sub>Recent players: {recent}</sub>\n\n"
        "</div>"
    )


def inject(state):
    text = README_PATH.read_text(encoding="utf-8")
    block = f"{START}\n{render(state)}\n{END}"
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit("README.md is missing the TTT markers")
    README_PATH.write_text(pattern.sub(lambda _m: block, text), encoding="utf-8")


def remember(state, user):
    if not LOGIN_RE.match(user or ""):
        return
    recent = [u for u in state["recent"] if u != user]
    recent.insert(0, user)
    state["recent"] = recent[:5]


def play(state, title, user):
    if NEW_RE.match(title):
        if state["over"] or not any(state["board"]):
            state["board"] = [""] * 9
            state["over"] = False
            state["message"] = FRESH_MSG
            return "New game started. You are ❌ and I am ⭕. Pick a square on the profile board."
        return "A game is already in progress, so nothing was reset. Pick a square on the profile board."

    m = MOVE_RE.match(title)
    if not m:
        return "I could not read that move. Please use the links on the README board and leave the title as it is."
    if state["over"]:
        return "That game is finished. Use the Play again link on the profile to start a new one."

    i = int(m.group(1))
    if state["board"][i]:
        return f"Square {i + 1} is already taken. Reload the profile and pick an empty square."

    state["board"][i] = "X"
    remember(state, user)
    result = outcome(state["board"])
    if result is None:
        state["board"][bot_move(state["board"])] = "O"
        result = outcome(state["board"])

    if result == "X":
        state["over"], state["message"] = True, "You won! 🎉 Nicely played."
        state["stats"]["you"] += 1
    elif result == "O":
        state["over"], state["message"] = True, "I won this round. 🤖 Want a rematch?"
        state["stats"]["bot"] += 1
    elif result == "draw":
        state["over"], state["message"] = True, "It's a draw. 🤝 Want a rematch?"
        state["stats"]["draw"] += 1
    else:
        state["message"] = FRESH_MSG

    return f"You played square {i + 1}. {state['message']} Check the board on the profile."


def main():
    state = load()
    if len(sys.argv) > 1 and sys.argv[1] == "render":
        inject(state)
        return
    title = os.environ.get("TITLE", "").strip()
    user = os.environ.get("USER_LOGIN", "")
    comment = play(state, title, user)
    save(state)
    inject(state)
    COMMENT_PATH.write_text(comment + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
