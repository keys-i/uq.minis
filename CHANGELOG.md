# Changelog

## v0.17.0

- Require Python 3.15 and adopt its deferred-import support
- Keep optional mini dependencies out of unrelated command startup paths

Historical source release for development iteration 16; original code is preserved with version metadata updated to `0.17.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/a07c2ce9f1c22fcd0debf64a8c65513bc3460bc2...b51d7d8d4d87956a2c3fcccd3e53f45032e4cab1)

## v0.16.0

- Run the complete Linux test environment in GitHub Actions
- Make test failures and the coverage gate block CI, with reports available for inspection

Historical source release for development iteration 15; original code is preserved with version metadata updated to `0.16.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/376b5067362e4fd691335b90f79cf9b9d88c35fe...a07c2ce9f1c22fcd0debf64a8c65513bc3460bc2)

## v0.15.0

- Replace command-sheet skills with reusable task playbooks
- Document mini workflows, input inspection and deliverable checks in warm Australian English

Historical source release for development iteration 14; original code is preserved with version metadata updated to `0.15.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/a5ccadd0502cac1cce0d38b3b101b931f346c274...376b5067362e4fd691335b90f79cf9b9d88c35fe)

## v0.14.0

- Cover countdown rendering and upload validation
- Exercise media configuration and upload failure paths with controlled inputs

Historical source release for development iteration 13; original code is preserved with version metadata updated to `0.14.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/53e6f40c3d9a0be8ee8f7cc9988e52bff6cf962d...a5ccadd0502cac1cce0d38b3b101b931f346c274)

## v0.13.0

- Parameterise Scrappy export and menu tests
- Check course output and selection behaviour across representative inputs

Historical source release for development iteration 12; original code is preserved with version metadata updated to `0.13.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/9ec4d201d78861d9013dbc80d28f7e9ac3b2c15c...53e6f40c3d9a0be8ee8f7cc9988e52bff6cf962d)

## v0.12.0

- Cover mailbox safety and persistent worker recovery
- Exercise failures and resume behaviour without sending real email

Historical source release for development iteration 11; original code is preserved with version metadata updated to `0.12.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/342d9379f604aa84fd01beff8a8543b3d8669b95...9ec4d201d78861d9013dbc80d28f7e9ac3b2c15c)

## v0.11.0

- Separate reusable test setup from individual test cases
- Parameterise CLI coverage and reduce repeated fixtures

Historical source release for development iteration 10; original code is preserved with version metadata updated to `0.11.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/2466a94b3d7ad48523cc5fd8f5bd88f6c76c351b...342d9379f604aa84fd01beff8a8543b3d8669b95)

## v0.10.0

- Give each mini its own command registration in `src/cli/`
- Share Typer, Rich and prompt infrastructure; keep domain logic in each mini folder

Historical source release for development iteration 9; original code is preserved with version metadata updated to `0.10.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/ba9e751af66f19ba84be4116e00a9ba15155e2e6...2466a94b3d7ad48523cc5fd8f5bd88f6c76c351b)

## v0.9.0

- Add validated YouTube upload drafts and uploads
- Check metadata and upload choices before sending a generated video

Historical source release for development iteration 8; original code is preserved with version metadata updated to `0.9.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/d3cab49976ec500419c5d61a42c18e3e36753ebc...ba9e751af66f19ba84be4116e00a9ba15155e2e6)

## v0.8.0

- Add countdown rendering with reusable media inputs
- Validate timer settings and retain editable configuration alongside generated video output

Historical source release for development iteration 7; original code is preserved with version metadata updated to `0.8.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/6b1b7d15e5bcf26b7fbe03ff3614fca9c56189fc...d3cab49976ec500419c5d61a42c18e3e36753ebc)

## v0.7.0

- Add countdown styles and reusable bundled artwork
- Keep fonts and visual assets in `docs/assets/` for predictable offline use

Historical source release for development iteration 6; original code is preserved with version metadata updated to `0.7.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/9465564aeee75255e0d1da323c735104a026a227...6b1b7d15e5bcf26b7fbe03ff3614fca9c56189fc)

## v0.6.0

- Share cache publication, size budgets and eviction across minis
- Keep Scrappy-owned cache and state under `.minis/scrappy/`

Historical source release for development iteration 5; original code is preserved with version metadata updated to `0.6.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/0990b3118d335e301b7b9db57f476b3222f8ed69...9465564aeee75255e0d1da323c735104a026a227)

## v0.5.0

- Add campus, building and room selection during event setup
- Filter rooms by capacity, preview virtual tours and apply the selected venue without rewriting the event TOML

Historical source release for development iteration 4; original code is preserved with version metadata updated to `0.5.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/964c6d784b945d03390a68d89122abf3985c6836...0990b3118d335e301b7b9db57f476b3222f8ed69)

## v0.4.0

- Move persistent mailbox processing into `src/worker/`
- Repair Outlook composition and preserve worker recovery behaviour

Historical source release for development iteration 3; original code is preserved with version metadata updated to `0.4.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/5a0ed7cdb3a9813600628fd800d6e62919855f43...964c6d784b945d03390a68d89122abf3985c6836)

## v0.3.0

- Move common helpers, consoles, prompts and terminal setup into `src/core/`
- Reuse shared infrastructure instead of maintaining separate mini implementations

Historical source release for development iteration 2; original code is preserved with version metadata updated to `0.3.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/7d7c7c3c53dc91cd1450036de537401fa08d4fe3...5a0ed7cdb3a9813600628fd800d6e62919855f43)

## v0.2.0

- Remove the minis MCP adapters, server discovery and MCP dependencies
- Keep the supported workflows available through skills and the CLI

Historical source release for development iteration 1; original code is preserved with version metadata updated to `0.2.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/a263ff886c25ec74caefa28bc3cf3190309c76a2...7d7c7c3c53dc91cd1450036de537401fa08d4fe3)
