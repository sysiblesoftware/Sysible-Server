# Sysible Workstation — auto-start tmux for interactive logins.
#
# The split-terminal keys (Ctrl+F1 etc., see /etc/tmux.conf) only do anything
# INSIDE tmux. On a headless server you'd otherwise land at a bare shell and the
# keys would appear "broken" until you manually ran `tmux`. So attach to (or
# create) a shared session on interactive login.
#
# Heavily guarded so it never breaks anything non-interactive:
#   - skip if already inside tmux ($TMUX) — no nesting/recursion
#   - skip non-interactive shells (scp/sftp/rsync, `ssh host cmd`, cron)
#   - skip dumb/again-less terminals and when stdout isn't a tty
#   - opt out entirely with  export SYSIBLE_NO_TMUX=1  (e.g. in ~/.bashrc)
#   - never abort the login if tmux misbehaves
if [ -z "$TMUX" ] && [ -z "$SYSIBLE_NO_TMUX" ] && command -v tmux >/dev/null 2>&1; then
  case "$-" in
    *i*)
      case "$TERM" in
        ""|dumb|network) : ;;    # not a real interactive terminal
        *)
          if [ -t 0 ] && [ -t 1 ]; then
            # -A: attach if the session exists, otherwise create it. Exec so
            # leaving tmux logs you out, as users expect from a login shell.
            exec tmux new-session -A -s main 2>/dev/null || true
          fi
          ;;
      esac
      ;;
  esac
fi
