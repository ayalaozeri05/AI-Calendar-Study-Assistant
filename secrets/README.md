# Google OAuth credentials (local only)

Place your Desktop OAuth client JSON here as:

```text
secrets/google_calendar_credentials.json
```

Or set `GOOGLE_CALENDAR_CREDENTIALS_PATH` in `.env` to another local path.

**Never commit** `*.json` credential files. They are ignored by `.gitignore`.

## Difference: OAuth credentials vs user tokens

| File | What it is | Shared? |
|------|------------|---------|
| `secrets/google_calendar_credentials.json` | Google Cloud **Desktop OAuth client** (client id/secret) | Same file for the app |
| `local_tokens/google_calendar/<user_id>.json` | Per-user **access + refresh token** after browser consent | One file per user |

User token files are created automatically after **Connect Google Calendar** and must stay out of Git.
