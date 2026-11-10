#!/usr/bin/env bash
# Reports what this machine and project have for delivery-loop.
# Read-only: it runs version checks and looks at the current project. Always exits 0.
ok()   { printf 'ok       %-9s %s\n' "$1" "$2"; }
miss() { printf 'missing  %-9s %s\n' "$1" "$2"; }

if command -v python3 >/dev/null 2>&1; then
  v="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
    ok python3 "$v"
  else
    miss python3 "$v found; the review runner needs 3.9 or later"
  fi
else
  miss python3 "the review runner needs Python 3.9 or later"
fi

if command -v git >/dev/null 2>&1; then ok git "$(git --version | head -1)"; else miss git "required"; fi

if command -v br >/dev/null 2>&1; then
  ok br "$(br --version 2>/dev/null | head -1)"
else
  miss br "the delivery-board skill needs br (beads_rust); the other skills work without it"
fi

if command -v codex >/dev/null 2>&1; then
  ok codex "$(codex --version 2>/dev/null | head -1) (sign-in not checked)"
else
  miss codex "no second-model review: the gate then runs lenses and finding verification only"
fi

if command -v gh >/dev/null 2>&1; then ok gh "optional, for PR and CI state on GitHub"; else miss gh "optional: PR and CI state on GitHub"; fi

if root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  ok project "$root"
  if [ -f "$root/CLAUDE.md" ] && grep -q "Delivery loop: project profile" "$root/CLAUDE.md"; then
    ok profile "found in CLAUDE.md"
  else
    miss profile "no project profile in CLAUDE.md; /delivery-loop:setup adds it"
  fi
  if [ -d "$root/.beads" ]; then ok board "$root/.beads"; else miss board "no .beads/ in this repository; the profile can point the board at another directory"; fi
else
  miss project "not inside a git repository; run this from the project you want to lead"
fi
exit 0
