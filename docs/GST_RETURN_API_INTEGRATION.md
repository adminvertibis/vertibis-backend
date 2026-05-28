# GST Return API Integration

This integration uses the CharteredInfo GST Return Filing API for read-only report data ingestion.

It intentionally does not expose return filing, save, offset, liability payment, or return modification endpoints. Vertibis only fetches return data for MSME health scoring and advisory analysis after client consent.

## Provider

- Sandbox base URL: `https://gstsandbox.charteredinfo.com`
- Production base URL: `https://gstapi.charteredinfo.com`
- API family used: GST Return Filing API
- Read-only returns used first: GSTR-1, GSTR-3B, GSTR-2B

## Environment

Set these on Railway/Vercel backend environment before enabling live calls:

```bash
GST_API_REMOTE_ENABLED=true
GST_API_ENV=sandbox
GST_SANDBOX_BASE_URL=https://gstsandbox.charteredinfo.com
GST_PROD_BASE_URL=https://gstapi.charteredinfo.com
GST_ASP_ID=...
GST_ASP_PASSWORD=...
GST_API_COST_PER_CALL=10
GST_TIMEOUT_SECONDS=30
GST_TOKEN_SECRET=...
```

Do not put ASP credentials in frontend code, Git, or public logs.

## Partner Flow

1. CA creates/selects the client.
2. Client consent is signed through Vertibis consent flow.
3. CA enters GST portal username and requests OTP.
4. CA enters OTP and Vertibis generates a short-lived GST auth token.
5. CA selects single month or period range and return types.
6. Vertibis fetches read-only return data, stores raw and normalized payloads, and records one costing log per API call.
7. CA generates the report preview.
8. Final PDF/share/export remains controlled by the report credit unlock flow.

## Read-Only Endpoints Implemented

- `GET /taxpayerapi/dec/v1.0/authenticate?action=OTPREQUEST`
- `GET /taxpayerapi/dec/v1.0/authenticate?action=AUTHTOKEN`
- `GET /taxpayerapi/dec/v2.1/returns/gstr1?action=RETSUM`
- `GET /taxpayerapi/dec/v2.1/returns/gstr1?action=B2B`
- `GET /taxpayerapi/dec/v0.3/returns/gstr3b?action=RETSUM`
- `GET /taxpayerapi/dec/v3.0/returns/gstr3b?action=AUTOLIAB`
- `GET /taxpayerapi/dec/v1.0/returns/gstr2b?action=GET2B`

## Application Endpoints

- `POST /api/v1/clients/{client_id}/gst/request-otp`
- `POST /api/v1/clients/{client_id}/gst/auth-token`
- `POST /api/v1/clients/{client_id}/gst/fetch`

All three require an authenticated partner session and a matching client GSTIN. Fetching requires valid consent and an active OTP-generated auth token.

## Data Storage

- `gst_auth_sessions`: OTP/auth token session metadata.
- `gst_fetch_batches`: one row per single-month or batch fetch.
- `gst_api_fetch_logs`: one row per external GST API call with masked endpoint and estimated cost.
- `gst_return_raw_data`: provider payloads by return type/action/period.
- `gst_return_normalized_data`: scoring-ready summaries by return type/period.

The upload/report generation route merges the latest normalized GST return data when `gst_fetch_requested=true`.

## Cost Visibility

`GST_API_COST_PER_CALL` defaults to `10`. Each actual GST API call writes a `gst_api_fetch_logs` row with `estimated_cost`, and each batch stores total expected calls and total estimated cost.

