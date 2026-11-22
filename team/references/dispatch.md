# Bind a canonical role to a real independent child

Two transports implement the same research role. Neither supplies the original
TradingCodex service authentication or enforced per-role permissions.

- `native-profile`: when the actual tool exposes a verified profile selector,
  select the matching canonical profile. Do not guess parameter names.
- `explicit-role-instructions`: when it only exposes a message/task and child
  lifecycle (for example collaboration.spawn_agent), use the protocol below.
  This is the supported message-based transport, not runtime profile registration.

Missing a selector is not a reason to stop. Missing real subagent delegation is.
Do not install a server, alter host configuration, or open another user chat.

## Dispatch

1. Resolve an absolute package root containing AGENTS.md, START-HERE.md,
   `.codex/agents/` and this skill. Use absolute paths in briefs; child working
   directories may differ. Do not depend on automatic skill/profile discovery.
2. Read `.codex/agents/<role>.toml`. Pass its complete `developer_instructions`
   text in the child message unchanged, together with the absolute root and
   exact absolute paths to that TOML, `child-contract.md`, `records.md`, and
   `methods/<role>.md`. In this transport the text is a task instruction, not
   an injected developer-level message. Higher-priority host rules still apply.
3. Include mandate path, scope, exact input versions, data owner, output path,
   and the question. Require the child to read the canonical files before work
   and acknowledge their paths and role in its report. Do not provide an expected
   conclusion. For reviews, provide the accepted conclusion as the object of
   challenge, never as an instruction to agree.
4. Invoke a real child tool. Where `fork_turns` exists, set it to `none` for fresh
   context. Do not set model/reasoning overrides. Record the actual returned child
   ID and transport before accepting any result. `task_name` is a label, not a
   role selector or authenticated identity. A fresh reviewer must be different
   from the producer and Head Manager; never repurpose the producer as reviewer.
5. Wait on the observed child ID. Read its actual report; verify role/file
   acknowledgment, assigned output path, inputs and scope. If it missed the
   role contract, request correction from that same child before acceptance.
   Readback and computed hashes detect mistakes, not authorship or obedience.
6. Record transport, canonical paths, observed child ID, file readback and
   acceptance. Corrections go to that child using its existing ID. Keep prior
   report versions. Only a different material specialty warrants a new child.

The same binding procedure applies to all nine roles. In particular risk and
judgment require their full canonical methods, distinct role-owned outputs and
independent children. Never replace them with a generic 'be critical' prompt.
If files, fresh independent children, or required accepted inputs are missing,
record blocked/waiting for the affected result. A tool failure is never success.

## Brief shape

Use the actual native tool schema, with this content as its message:

```text
Package root: <absolute path>
Transport: explicit-role-instructions
Assigned role: <exact role>
Canonical profile: <absolute .toml path>
<complete developer_instructions from that profile, without rewriting>
Resolve all relative references against Package root. Before substantive work,
read <absolute child-contract>, <absolute records>, <absolute role method>.
Read mandate <absolute path>. Inputs: <exact accepted versions or source paths>.
Question: <bounded causal question>. Data family owner: <role/identity>.
Write only <assigned versioned output path/directory>.
Include role, transport, canonical files read and normal report metadata.
Do not spawn a team, modify package/configuration, browse beyond scope, access
accounts or place orders. Return the actual saved path and remaining gaps.
```
