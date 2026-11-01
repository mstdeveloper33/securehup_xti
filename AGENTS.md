# XTI development rules

- Read `docs/STATUS.md` for implemented scope and `docs/ARCHITECTURE.md` for boundaries.
- The roadmap describes future work. Do not report a planned feature as implemented.
- Keep domain rules independent of storage, terminal, HTTP and external services.
- Application services depend on small ports; wire concrete adapters at the entry point.
- Use Python 3.11 or newer. `./scripts/check` runs the local verification suite.
- Preserve existing user data. Schema changes require an explicit migration and recovery strategy.
- Never silently overwrite backups or restore onto an existing database.
- Test meaningful persistence, validation, recovery and user-facing behavior for changes to them.
- External collection belongs behind a source port and adapter. Public certificate and existing web-scan archive searches are authorized; keep new scan submissions and active target probing separate from these passive collectors.
- Treat external strings as untrusted; do not interpolate them into shell commands or terminal markup.
- Keep secrets, runtime databases and collected evidence out of source control.
- Add dependencies only for a concrete need; document architectural decisions in `docs/decisions/`.
- Update the usage and current status when behavior changes. Explain user-facing changes in plain Turkish.

