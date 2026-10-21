# Ticket status and notes: ElevenLabs setup

The backend endpoints are `/tools/ticket-status` and `/tools/ticket-note`. The agents live in ElevenLabs, so the two
tools and the prompt lines below are added there by hand, then backed up with `scripts/export_elevenlabs.py`.

## Tools (Sam only)

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
  changed or when someone will be on site. Only call it when the caller tells you something new for the team, never
  to record that they called or had nothing to add. Only works for the caller's own tickets."
- Body (`ticket_id` and `note` required):
  - `ticket_id` (string): "The ticket number, for example NS-4821."
  - `note` (string): "What the caller wants added, in one or two plain sentences. Never include alarm codes or passwords."
  - `customer_id`, `callback_number`, `conversation_id`: as above

## Prompt lines

Sam, in `# Goal`, after the front desk steps (as published; from `elevenlabs/agents/sam.json`):

```
Existing ticket (the caller asks about a ticket they already have, or wants to add something to it):
4. Find the account first, exactly as in step 3: ask for the phone number on the account or the business name and call lookup_customer. Do not ask for the ticket number until the account is found. If there is no match after one retry, don't guess: say you can't pull up a ticket without finding the account, and take a message for the service desk instead (see Front desk).
5. Once the account is found, ask for the ticket number if they have it. Call check_ticket_status with the ticket_id (if given), the customer_id from lookup_customer, and the confirmed callback number. Tell the caller what tell_the_caller says, in your own words. Only the status is known: never say anyone will call, visit, arrive, or be in touch, and never give or guess a time or a technician's name. If they ask when, say you don't have a time on the ticket and offer to add a note asking for an update.
6. Only if the caller tells you something new for the team, call add_ticket_note with their words in one or two sentences. Never add a note just to record the call or that they had nothing to add. If what they say means the problem is worse or is now an emergency, handle it as a service report too.
```

Jordan doesn't have these tools: a billing caller who asks about a repair ticket gets a message for the service
desk (`take_message`), as before.

## Evaluation Lab tests

`scripts/create_ticket_lab_tests.py` creates QA-22 (another account's ticket gets no details), QA-23 (no note when the
caller says nothing new) and QA-24 (no promised times or technician contact) in ElevenLabs and runs each three times.
It needs a key that can write agent tests, and prints the test ids for `qa_lab.TESTS`.
