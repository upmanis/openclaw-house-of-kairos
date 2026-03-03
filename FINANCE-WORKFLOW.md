## Automated Flows

### Send to Finance

**⚡ CRITICAL: When Kaspars says "send to finance" — DO NOT ASK QUESTIONS. Execute immediately.**

This is a fully automated flow. When triggered, find the file, extract details, send email, confirm. Zero questions.

#### Trigger detection

The flow triggers when ALL of these are true:
1. Message is a **DM from Kaspars** (+37120000453) — never groups
2. Message text contains **"send to finance"** (case-insensitive, partial match OK)
3. A **file attachment** (PDF or image) exists in the current message OR in a recent preceding message

#### How to find the attachment

WhatsApp attachments appear in the message text as:
```
[media attached: /Users/ai/openclaw/media/inbound/FILENAME---UUID.ext (mime/type)]
```

**⚠️ IMPORTANT: Media messages often arrive AFTER the text message due to download/processing time. The "send to finance" text may arrive before the PDF. You MUST check all sources before responding.**

**Search order (check ALL before sending any reply):**
1. Check the CURRENT message for `[media attached:` — the file and "send to finance" may be in the same message
2. If not found, check PRECEDING messages in the conversation for `[media attached:`
3. If still not found, **check the media directory for recent files:**
   ```bash
   ls -lt /Users/ai/openclaw/media/inbound/ | head -5
   ```
   Look for files modified in the last 2–3 minutes. If you find one, use it.
4. If still nothing, **wait 10 seconds and check the media directory again** — the file may still be downloading:
   ```bash
   sleep 10 && ls -lt /Users/ai/openclaw/media/inbound/ | head -5
   ```
5. If STILL no file after waiting, ONLY THEN reply: "I don't see a file — could you share the invoice?"

**🚨 ONE REPLY ONLY: You must send exactly ONE WhatsApp message for this flow — either the success confirmation (Step 3) or the "no file" fallback. NEVER send both. Do all checking silently before responding.**

#### Step 1: Extract invoice details

**For PDFs** (mime = `application/pdf`):
```bash
pdftotext /Users/ai/openclaw/media/inbound/FILENAME---UUID.pdf -
```
Then parse the text output for: vendor name, invoice number, date, due date, total amount, balance due, line items, notes.

**For images** (mime = `image/jpeg`, `image/png`, `image/heic`):
Use the Read tool to view the image, then extract the same fields via vision/OCR.

**If extraction fails** (garbled text, scanned image, etc.): Don't stop — proceed to Step 2 with fallback values.

#### Step 2: Send email (NO confirmation — just send it)

```bash
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail send \
  --to "finance@houseofkairos.com" \
  --cc "kaspars@houseofkairos.com" \
  --subject "Please submit - {amount} {vendor}" \
  --attach "/Users/ai/openclaw/media/inbound/FILENAME---UUID.pdf" \
  --body-file - \
  -a ops@houseofkairos.com <<'EOF'
Hi team,

Please process the attached invoice:

- Vendor: {vendor}
- Invoice #: {invoice_number}
- Date: {date}
- Due date: {due_date}
- Total: {amount}
- Balance due: {balance_due}

{line_items_or_notes_if_any}


Chief of Staff, House of Kairos
EOF
```

**Subject format:** `Please submit - {amount} {vendor}` (e.g., "Please submit - Rp8,850,000 Rezeki Meubel")

**If extraction failed**, use:
- Subject: `Please submit - see attachment`
- Body: "Please see the attached invoice for processing."

**Multiple files, same vendor:** Add multiple `--attach` flags in one email.
**Multiple files, different vendors:** Send separate emails per vendor.

#### Step 3: Confirm to Kaspars

Reply on WhatsApp: "Sent to finance: {vendor} — {amount}. You're CC'd."

If extraction failed: "Sent to finance (couldn't read invoice details, but file is attached). You're CC'd."

#### What NOT to do

- **DO NOT reply immediately** if the attachment isn't in the current message — check media directory and wait first
- **DO NOT send multiple messages** — the entire flow produces exactly ONE WhatsApp reply (the confirmation)
- **DO NOT ask** what file to send — find it via the search order above
- **DO NOT ask** what email address — it's always finance@houseofkairos.com
- **DO NOT ask** for subject/CC/notes — they're defined above
- **DO NOT ask** for confirmation before sending — just send
- **DO NOT trigger** from group chats, non-Kaspars contacts, or messages without "send to finance"
