# The QA-Genius skill for Claude

`SKILL.md` tells Claude when to reach for QA-Genius and in what order to
call its tools. It is a few hundred words; the tools themselves carry
their own descriptions, so the skill only has to cover the things a tool
description cannot: the order, what to do with `ask_the_po`, and never
claiming a check passed that never ran.

The skill needs the MCP server connected. Do that first.

## 1. Connect the server

**Claude Code**

```
claude mcp add --transport http qa-genius https://qa-genius-ashy.vercel.app/mcp
```

Check it worked:

```
claude mcp list
```

**Claude app, Claude Cowork**

Customize → Connectors → Add custom connector → paste
`https://qa-genius-ashy.vercel.app/mcp`.

There is nothing to sign in to and no key to paste. If the server answers
`404`, `/mcp` is switched off on that deployment — see
`docs/mcp.md` for the environment variable that turns it on.

## 2. Install the skill

**Claude Code** — copy the folder into either place:

```
# just you, every project
cp -r integrations/claude/qa-genius ~/.claude/skills/

# this repository, everyone who clones it
mkdir -p .claude/skills
cp -r integrations/claude/qa-genius .claude/skills/
```

Start a new session and ask Claude to "check this story with QA-Genius".

**Claude app** — Settings → Capabilities → Skills → upload the
`qa-genius` folder.

## 3. Try it

Paste a user story and say:

> Use qa-genius to check this story, then write the criteria and tests and
> check those too.

Claude should call `check_story`, write criteria and tests, call
`review_tests`, fix what comes back, call it again, and finish with
`ship_check` and a report link.

## Without the skill

The skill is a convenience, not a requirement. The server's own
instructions carry the same tool order, and Claude reads those when it
connects. The skill mainly helps Claude decide *when* QA-Genius is the
right thing to reach for, and keeps it honest about `ask_the_po` and
about checks that never ran.
