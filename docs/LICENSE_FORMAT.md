# Mercury SkyPulse license format

License documents are UTF-8 JSON and limited to 64 KiB. Version 1 has exactly
four top-level fields:

```json
{
  "schema": 1,
  "key_id": "vendor-2026-01",
  "payload": {
    "license_id": "01JEXAMPLE",
    "edition": "enterprise",
    "subject": "County Emergency Communications",
    "subject_type": "organization",
    "organization": "Example County ARES",
    "deployment_id": "operations-center",
    "seats": 50,
    "issued_at": "2026-01-01T00:00:00Z",
    "not_before": "2026-01-01T00:00:00Z",
    "expires_at": "2027-01-01T00:00:00Z",
    "features": ["custom.reporting"]
  },
  "signature": "BASE64URL_ED25519_SIGNATURE_WITHOUT_REQUIRED_PADDING"
}
```

Supported editions are `community`, `standard`, `professional`, and
`enterprise`. Subject type is `individual` or `organization`. Organizational
licenses require `organization`; `deployment_id` and `seats` are optional
administrative metadata. `expires_at` may be `null`. All timestamps require an
offset and are normalized to UTC. Feature names use lowercase letters, digits,
dots, and hyphens.

## Signature input

The Ed25519 signature covers a new object containing only `schema`, `key_id`, and
`payload`. Serialize it as UTF-8 JSON with recursively sorted keys, no insignificant
whitespace, literal non-ASCII characters, and separators `,` and `:`. In Python:

```python
message = json.dumps(
    {"schema": 1, "key_id": key_id, "payload": payload},
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
signature = private_key.sign(message)
```

Private keys belong in the external issuance environment and must never be
installed with Mercury SkyPulse. Deploy raw 32-byte Ed25519 public keys through
the trusted-key registry documented in the README. Signing-key rotation is done
by adding the new public key before issuing licenses with its `key_id`, then
removing retired keys after their licenses are no longer accepted.

This format provides offline authenticity and entitlement metadata. It does not
provide confidentiality, copy protection, activation, or machine binding.
