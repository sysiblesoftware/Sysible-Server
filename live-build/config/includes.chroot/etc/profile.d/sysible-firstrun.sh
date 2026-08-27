# Sysible Workstation — offer the optional / external software menu on first login.
#
# Some tooling can't be baked into the distributed image for LICENSING reasons
# (HashiCorp's BUSL products, the AWS CLI installer, etc.), so `sysible-tools`
# installs it on demand AFTER boot — the license choice stays the operator's. But
# nothing surfaced that menu, so a fresh install "never prompted for external
# software". This prompts ONCE, on the first interactive login, and launches the
# menu if the operator wants it.
#
# Guarded like the tmux auto-start so it never breaks a login:
#   - interactive shells with a real TTY only (skips scp/sftp/cron/`ssh host cmd`)
#   - skipped once answered (a per-user marker), and inside tmux
#   - opt out entirely with  export SYSIBLE_NO_FIRSTRUN=1
#   - runs BEFORE sysible-tmux.sh (alphabetical) so the tmux exec doesn't swallow it
if [ -z "$SYSIBLE_NO_FIRSTRUN" ] && [ -z "$TMUX" ] && command -v sysible-tools >/dev/null 2>&1; then
  case "$-" in
    *i*)
      if [ -t 0 ] && [ -t 1 ]; then
        _sysible_mark="${XDG_STATE_HOME:-$HOME/.local/state}/sysible/tools-prompted"
        if [ ! -e "$_sysible_mark" ]; then
          mkdir -p "$(dirname "$_sysible_mark")" 2>/dev/null || true
          : > "$_sysible_mark" 2>/dev/null || true
          printf '\n\033[1;32mWelcome to Sysible Workstation.\033[0m\n'
          printf 'Optional / external software (Terraform, Vault, Consul, Nomad, Packer,\n'
          printf 'Boundary, AWS CLI) is NOT installed by default — for licensing reasons the\n'
          printf 'choice is yours. OpenTofu (tofu), gcloud and the Azure CLI already ship.\n\n'
          printf 'Open the software menu now to pick what to install? [y/N] '
          read -r _sysible_ans </dev/tty 2>/dev/null || _sysible_ans=n
          case "$_sysible_ans" in
            [Yy]*) sysible-tools || true ;;
            *)     printf 'Skipped. Run \033[1msysible-tools\033[0m any time to install them later.\n\n' ;;
          esac
          unset _sysible_ans
        fi
        unset _sysible_mark
      fi
      ;;
  esac
fi
