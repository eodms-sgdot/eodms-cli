# User Profile API Notes

Notes copied from developer-provided test examples.

## Endpoint

Send a `PATCH` request to:

```text
/aaa/v1/users/USERNAME
```

The request body is JSON. The original notes list these payload keys: `language`, `address`, `email`, `surname`, `given_name`, and `password`. Multiple fields can be updated in one request. The examples below preserve the noted shapes, with personal values replaced by placeholders.

```json
{"language": "English"}
```

```json
{
  "address": {
    "@type": "main",
    "country": "Canada",
    "province": "quebec",
    "postal-code": "a1a 1a1"
  }
}
```

```json
{"email": "user@example.com"}
```

```json
{"surname": "Smith"}
```

```json
{"password": "MyNewPassword123!@"}
```

A `GET` request to the same endpoint returns the user's profile.

## Current CLI Note

The current `user update` CLI does not accept `language` as an update field or `password` in a profile payload. Use `user change-password` to change a password. The API notes above record the original developer examples and should not be treated as confirmation that every payload is accepted by the current CLI or staging API.