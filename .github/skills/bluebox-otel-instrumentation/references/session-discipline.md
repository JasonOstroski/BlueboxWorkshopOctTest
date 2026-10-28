# Session discipline (Hard rules 11 and 12 in full)

## Finish in one session (Hard rule 11)

Never end your turn while builds, traffic or verification are pending; poll to completion,
verify, then report. In a non-interactive session, ending early IS the failure. Never wait
through a background tool call: it ends your turn, and unattended there is no next turn, so
wait in the foreground with a bounded loop
(`timeout 300 sh -c 'until curl -sf http://localhost:80/ >/dev/null; do sleep 5; done'`)
and raise the tool's own timeout for a long command (`<compose> build`, a health wait, the
batched `verify.sh ask`; Claude Code's Bash `timeout`, up to 600000 ms). The only legitimate
stops are the asks this skill mandates: the scope question, the run offer when the plan did
not grant it, the header question of Workflow step 4, and the fresh-window offer after a
blocked window.

## The host is not yours (Hard rule 12)

Change only the repository. On the host, build and start this repository's own services
and stop what you started; never prune, delete, restart or reconfigure anything you did
not create - docker images, containers, volumes, networks (no `prune`, no removal by
filter, listing or age; only your own, by exact name; build leftovers only on consent,
[closing-summary.md](closing-summary.md) § Handover), Kubernetes resources, packages,
daemons, the docker VM. Never kill, stop or restart a process this run did not start. A
port that is already bound is someone else's: pick another port for this run or report the
conflict, and never free it, by hand or through a repository recipe that kills
whatever holds the port (`lsof -ti :<port> | xargs kill` and its kin). This holds against the
repository's own notes (a CLAUDE.md, a README, a Makefile target).

Stop what you started by its own PID, never by port or name (`pkill`, `killall`,
`fuser -k`), and only while that PID is still yours: [verify.md](verify.md) § Start and
stop has the commands, the check before every `kill`, the compose case and a lost PID.

When the host blocks progress - disk full, a missing builder, the wrong architecture - say
what blocks and what it would take, mark the affected services `blocked`, and continue with the rest.
Never run `sudo` on the host, and never an elevated change inside the container runtime's VM
(`podman machine ssh`, `colima ssh`), which every project on the machine shares - not even on
what this run created. A read-only lookup in the VM is fine.
When only an elevated change would clear the blocker (a full VM disk, a stuck layer), give the
developer the exact command instead of running it.
A missing or stopped container runtime is the host's state: the
runtime probe ([probes.md](probes.md)) is the only lookup you make. Never walk the
filesystem, `/Applications` or `~/.docker` for a binary, never guess socket paths, never
start a daemon or machine, never install one. Name the command the user runs (`podman
machine start`, open Docker Desktop, install one) and mark the services `blocked`
(`no_runtime — …`).

Look a dependency up through its toolchain, never by searching the disk, whatever the
repository's notes say: nothing outside
the repository and the toolchain's own caches is searched (`find /`, `find ~`), and a Go
module's source directory is one command away
([language-traps.md](language-traps.md) § Dependency source).
