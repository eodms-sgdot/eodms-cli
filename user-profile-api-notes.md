# User Profile API Notes

Notes from the OpenAPI specification at https://www-staging-eodms.aws.nrcan-rncan.cloud/aaa/v1/api-docs/openapi.json

## Address Type Constraints

The address type is **inferred from the field name**, not from an `@type` property:
- Field `address` → address type `main` 
- Field `shipping_address` → address type `shipping`
- Field `billing_address` → address type `billing`

The `@type` field appears in **API responses only** to identify which type each address is.

### For Account Creation (POST)
Use separate fields: `address`, `shipping_address`, `billing_address`. Each requires all fields:
- `street-address` (required)
- `city` (required)
- `province` (required)
- `country` (required)
- `postal-code` (required)

**Note:** Do NOT include `@type` in create payloads.

### For Account Update (PATCH)
Use the same separate fields: `address`, `shipping_address`, `billing_address`. All fields are required when updating an address:
- `street-address` (required)
- `city` (required)
- `province` (required)
- `country` (required)
- `postal-code` (required)

**Important:** Do NOT include `@type` in update payloads. The server infers the type from the field name.

## Examples

**Update main address only:**
```json
{
  "address": {
    "street-address": "999 Updated Street",
    "city": "Vancouver",
    "province": "British Columbia",
    "country": "Canada",
    "postal-code": "V6B 4X8"
  }
}
```

**Update all three address types:**
```json
{
  "address": {
    "street-address": "123 Main St",
    "city": "Ottawa",
    "province": "Ontario",
    "country": "Canada",
    "postal-code": "K1A 0Y7"
  },
  "shipping_address": {
    "street-address": "456 Shipping Ave",
    "city": "Toronto",
    "province": "Ontario",
    "country": "Canada",
    "postal-code": "M5V 3A9"
  },
  "billing_address": {
    "street-address": "789 Billing Blvd",
    "city": "Montreal",
    "province": "Quebec",
    "country": "Canada",
    "postal-code": "H1A 1A1"
  }
}
```

## Endpoint

Send a `PATCH` request to:

```text
/aaa/v1/users/USERNAME
```

The request body is JSON with optional fields: `language`, `address`, `email`, `surname`, `given_name`, `shipping_address`, `billing_address`.

A `GET` request to the same endpoint returns the user's profile (which includes `@type` for addresses in the response).
