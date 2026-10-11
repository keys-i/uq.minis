# Changelog

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
