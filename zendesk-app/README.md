# NightAgent Call (Zendesk sidebar app)

A private Zendesk Support app for the ticket sidebar. On a ticket NightAgent made after a call, it shows the call summary, priority, caller name, each tool call in order (with any that failed), the call check (rules and AI-judged items marked), and the transcript with phone numbers cut to the last four digits. Other tickets get a one-line note. It only reads.

It calls `GET /api/zendesk/tickets/{id}` on the NightAgent backend (`app/routes_sidebar.py`). The secret is a Zendesk **secure setting** limited to request headers and to `nightshift-dispatch.vercel.app`: Zendesk's proxy adds it to the request, so it never reaches the agent's browser and isn't in this folder.

## Files

- `manifest.json`: sidebar location, the secure setting, the allowed domain
- `translations/en.json`: names and the settings label
- `assets/iframe.html`, `main.js` (fetch), `render.js` (draws it, text only, no `innerHTML`), `style.css`, logos

## Install

Zendesk's local app server can't use secure settings, so try it by uploading it as a private app.

1. Log in once: `npx @zendesk/zcli login -i` (your Zendesk subdomain and an admin account).
2. Check it: `npx @zendesk/zcli apps:validate zendesk-app`
3. Upload and install: `npx @zendesk/zcli apps:create zendesk-app`. When asked for **Sidebar secret**, paste the `SIDEBAR_SECRET` value from Vercel.
   (Or `npx @zendesk/zcli apps:package zendesk-app` and upload the zip in Admin Center → Apps and integrations → Zendesk Support apps → Upload private app.)
4. Open a ticket NightAgent made and look in the apps panel on the right.

After a change, bump `version` in `manifest.json` and run `npx @zendesk/zcli apps:update zendesk-app`.

## Test without Zendesk

`node e2e/zd-sidebar-test.js` loads these files in headless Chrome with a stand-in for Zendesk's SDK: the request it makes, every state (call, still analyzing, 404, 401, 429, 503, network error, unsaved ticket), and that transcript text can't inject markup. It saves `e2e/zd-sidebar.png`.
