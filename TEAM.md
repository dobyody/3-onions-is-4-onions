# Agent workspace

One human owns each role and starts its matching agent. Each agent starts inside its own folder. It reads the sibling folders and shared protocol, writes its own folder, and uses its own `STATUS.md` as an outbox. This is a coordination convention. The folder layout itself does not set filesystem permissions.

## One computer or shared checkout

Open four terminal tabs at the extracted project root. Run one command per tab. These commands use an installed, signed-in Codex CLI.

```powershell
./start-role.ps1 transmitter
./start-role.ps1 receiver
./start-role.ps1 scope
./start-role.ps1 demo
```

In the Codex app or another agent UI, start one session per role folder and paste the corresponding [transmitter](01-transmitter/START.md), [receiver](02-receiver/START.md), [scope](03-scope/START.md) or [demo](04-demo/START.md) prompt. Keep the extracted parent project accessible so agents can read sibling files. With a shared checkout, updates become visible when other agents reread them.

## Four computers

Put the extracted project into one team Git repository. The integrator creates the base commit. Each teammate clones the repository, creates a role branch from the same base and starts the agent from its folder. Push role commits or PRs for handoffs. For an urgent cross-branch message, post the status link and commit or PR in your team chat. The integrator reviews and merges role changes. Each owner fetches and merges the updated main branch into their role branch at handoffs. An edit on another laptop becomes visible after Git sync. Keep generated videos out of Git unless the team deliberately adds small fixtures, and share large clips through a team-authorized location.

## Read and write the agent outboxes

| Owner | Outbox | Typical handoff |
| --- | --- | --- |
| Transmitter | [01-transmitter/STATUS.md](01-transmitter/STATUS.md) | Reference packet verified, sender run command and transmit log format |
| Receiver | [02-receiver/STATUS.md](02-receiver/STATUS.md) | Decode command, tested fixture and known failure modes |
| Scope | [03-scope/STATUS.md](03-scope/STATUS.md) | Sample frame, profile/spectrum output and calibration status |
| Integration | [04-demo/STATUS.md](04-demo/STATUS.md) | Recording location, regression results and rehearsal blockers |

1. Read the contract, [decisions](04-demo/DECISIONS.md) and all four outboxes when starting, when blocked, and before a handoff. In an interactive agent session, the human can ask the agent to check again as new messages arrive.
2. Add messages to your own outbox with sender, recipient, status and the path or commit the recipient should inspect. Recipients acknowledge in their own outbox. Keep coding from the reference packet while waiting for a dependency.
3. Propose shared interface changes in your outbox and tag impacted roles. Integration records an agreed revision in `04-demo/DECISIONS.md` after affected owners acknowledge it. Keep the initial root contract and fixture fixed during the first pass.
4. Post a run command and verification result at handoff. Each role writes only its own folder. Integration can write glue under `04-demo/` and can ask the owner to repair component issues.

## Checkpoints

| When | Team outcome |
| --- | --- |
| First 15 minutes | Read contract, check phone recording and browser playback, begin independent fixture work |
| First quarter of build time | Encoder matches vector, receiver decodes synthetic samples, scope recovers synthetic period, integration defines trial sheet |
| Halfway | First physical capture decoded or failure isolated to exposure, crop or timing |
| Final quarter | Freeze interfaces, capture fallback video, run trials and rehearse |
