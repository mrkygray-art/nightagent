# Ticket status and notes: ElevenLabs setup

The backend endpoints are `/tools/ticket-status` and `/tools/ticket-note`. The agents live in ElevenLabs, so the two
tools and the prompt lines below are added there by hand, then backed up with `scripts/export_elevenlabs.py`.

## Tools (add both to Sam and to Jordan)

Both are webhook tools: `POST`, header `x-tool-secret` set to the tool secret, response timeout 20 seconds, the same as
`billing_lookup`.

### `check_ticket_status`

- URL: `https://nightshift-dispatch.vercel.app/tools/ticket-status`
- Description: "Look up a ticket the caller already has, before telling them anything about it. Only works for the
  caller's own tickets. Returns the status in plain words and what to say."
- Body (none required):
  - `ticket_id` (string): "The ticket number the caller gives, for example NS-4821. Leave empty if they don't know it."
  - `customer_id` (string): "The customer_id returned by lookup_customer earlier in this conversation, for example C-1003."
  - `callback_number` (string): "The callback number the caller confirmed. Needed when there's no customer_id."
  - `conversation_id` (string): dynamic variable `system__conversation_id`

### `add_ticket_note`

- URL: `https://nightshift-dispatch.vercel.app/tools/ticket-note`
- Description: "Add what the caller wants the team to know to a ticket they already have, for example that the gate code
  changed or when someone will be on site. Only works for the caller's own tickets."
- Body (`ticket_id` and `note` required):
  - `ticket_id` (string): "The ticket number, for example NS-4821."
  - `note` (string): "What the caller wants added, in one or two plain sentences. Never include alarm codes or passwords."
  - `customer_id`, `callback_number`, `conversation_id`: as above

## Prompt lines

Sam, in `# Goal`, after the front desk steps:

```
Existing ticket (the caller asks about a ticket they already have, or wants to add something to it):
4. Find the account first (step 3), then ask for the ticket number if they have it.
5. Call check_ticket_status with the ticket_id (if given), the customer_id, and the confirmed callback number. Tell the caller what tell_the_caller says, in your own words. Never guess a technician's name or an arrival time.
6. If they want to add something, call add_ticket_note with their words in one or two sentences. If what they say means the problem is worse or is now an emergency, handle it as a service report too.
```

Jordan, in `# What to do`, step 5: "If the caller asks about a repair ticket they already have, call check_ticket_status
(or add_ticket_note to add something to it) instead of taking a message."

## Before calling it done

- Add an Evaluation Lab test for each (`qa_lab.TESTS`, with its `why`): someone else's ticket number must get no
  details, and a note must not be read back as a promise.
- Then drop the "Ticket status and notes" line from "Not measured yet" in the README, and update the public
  descriptions listed in CLAUDE.md.
