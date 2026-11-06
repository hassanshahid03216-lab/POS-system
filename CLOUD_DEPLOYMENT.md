# Cloud POS test deployment

The cloud setup uses a FastAPI service on Render and a PostgreSQL database on
Neon. Desktop clients talk to the API over HTTPS; the Neon connection string
stays on the API service and is never stored on cashier PCs.

## 1. Create the Neon database

1. Create a Neon project and database.
2. Run `neon env pull` to populate `.env.local` with `DATABASE_URL` and
   `DATABASE_URL_UNPOOLED`. The API uses the pooled URL for ordinary requests
   and the direct URL when it initializes the schema.
3. Keep the string private. Do not put it in source code, a committed `.env`
   file, or the desktop application's settings.

The API creates the ShopFlow schema during startup. The first workstation to
connect will show the owner setup flow because the cloud database starts with
no default user.

For a new, empty Neon branch, run `npm run build`, start the API locally, then
run `.venv\\Scripts\\python.exe scripts\\neon_smoke.py`. The smoke check refuses
to run if users already exist and removes its uniquely marked test records.

## 2. Deploy the API to Render

1. Push this repository to a Git provider that Render can access.
2. In Render, create a Blueprint from the repository and select `render.yaml`
   at the repository root. It defines the Python API web service.
3. Set both `DATABASE_URL` and `DATABASE_URL_UNPOOLED` in the Render service
   environment using the values from Neon. Render generates
   `API_SIGNING_SECRET` from the Blueprint.
4. Deploy and wait for `/health` to report `{"status":"ok"}`.
5. Copy the service's HTTPS URL, such as `https://shopflow-pos-api.onrender.com`.

The expected commands are `pip install -r api/requirements.txt` and
`uvicorn api.main:app --host 0.0.0.0 --port $PORT`.

## 3. Connect each POS computer

1. Install/run the desktop application on each computer.
2. On the sign-in screen, choose **Configure Cloud Server**.
3. Enter the Render HTTPS URL, without a trailing slash.
4. On the first computer only, create the shop owner's PIN. Add other staff
   through Settings after signing in.
5. Enter the same API URL on every other computer and sign in with the shared
   staff accounts.

Sales, products, customers, suppliers, returns, held bills, shifts, and
insights are stored in the shared database. Hardware selection and other
workstation preferences remain local to each PC.

## 4. Existing local data

This deployment starts with a new cloud database. Existing `pos.db` files are
not uploaded automatically. Before using the cloud database for a live shop,
plan and perform a one-time migration of the local store data.

## Test-tier limitations

Render's Free web service sleeps after 15 minutes without traffic, so the first
request afterward can be slow. Free hosting is intended for development and
testing, not live checkout. Neon and Render change free-tier quotas; check their
current plan limits before deploying.

## Local API development

Set `DATABASE_URL` and a stable `API_SIGNING_SECRET` in the local environment,
then run:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The desktop API URL can then be set to an HTTP local URL during development.
Production workstations must use HTTPS.
