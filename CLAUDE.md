# Working agreement

## 🚫 NEVER build an ISO unless explicitly told to — HARD RULE
Do **NOT** trigger a Sysible Server ISO build under any circumstances unless the
user, in that same message, explicitly tells you to build / kick / cut / rebuild
an ISO (e.g. running the `iso.yml` workflow / `workflow_dispatch`).

Committing and pushing changes is fine. **Building the ISO is not** — wait to be
told. Do not infer permission from "test it", "make a release", or the fact that
you built one earlier. If you think an ISO is needed, **ask first and stop**.

## Scope
This repo is the **headless server** base — no GUI. Keep it that way: do not add
GNOME, a display manager, Calamares, or desktop applications. GUI/desktop work
belongs in the Sysible Workstation repo
(https://github.com/sysiblesoftware/Sysible-Linux). Server-relevant tooling
(daemons, CLIs, container/orchestration/IaC, networking, observability,
hardening) is in scope.
