# Ivory Leads — first working foundation

Prepared for Mark Powell, 23 November 2026. This is an installable starting version, not the completed LeadStack replacement. It has not been deployed to TrueNAS.

## What works

- Password-protected, responsive single-owner dashboard (username `mark`).
- Manual prospects and CSV import/export, duplicate detection, notes, sales stages and follow-up dates.
- Apify Google Maps search connector: one industry and area, up to 25 results, requesting a $0.25 charge limit per run, with expensive enrichment/reviews/images disabled. Connect your own token first. Searches are started only when the owner presses the button.
- Refresh an existing run without buying another search. Imported results are deduplicated; closed businesses are skipped.
- Editable one-page website concepts in three colour treatments, based on supplied business details and confirmed services. No AI calls or image generation are included yet.
- Share links, private drafts, 30-day default expiry, no search indexing, no internal notes exposed on previews.
- Outreach text drafts only. No automatic sending, email delivery or SMS delivery exists in this release.

## Install on TrueNAS with Dockge

Repository: https://github.com/valianktni1/highleads

From the TrueNAS shell, create the persistent directories:

```sh
sudo mkdir -p /mnt/apps/highleads/data /mnt/photographers_data/highleadclients
```

The stack builds directly from this public GitHub repository. No local clone or source-directory mapping inside Dockge is required. No secrets or customer data belong in the repository.

Create a Dockge stack named `highleads`. Paste the complete repository `compose.yaml` into its YAML editor. Copy `.env.example` into the Dockge .env editor and set HIGHLEADS_PASSWORD to a unique password of at least 16 characters. APIFY_TOKEN can stay empty until lead searches are connected. The application secret is generated once at `/mnt/apps/highleads/data/.app-secret` and retained on restart; keep it in your secure backup.

Deploy/build the stack. Its prepare-storage service assigns ownership of only the two dedicated mounted directories to UID/GID 10001, without recursing over files. The main app then runs as that unprivileged identity. Data stays at `/mnt/apps/highleads/data`, and generated HTML snapshots stay at `/mnt/photographers_data/highleadclients`. Keep the source checkout separate from these data folders.

For future updates, rebuild the highleads service in Dockge so Docker fetches the current `main` branch and rebuilds the image. A normal restart alone does not update the source. GitHub access and dependency downloads must be available to the Docker builder.

In Nginx Proxy Manager use domain `highleads.ivorydigital.uk`, scheme HTTP, your NAS LAN IP, and forward port 30064. Enable a valid TLS certificate and Force SSL. Do not forward port 30064 from the internet router. Serve previews through the app, rather than exposing the clients directory as a static directory, so preview tokens and expiry remain enforced.

Open https://highleads.ivorydigital.uk and sign in as `mark` using HIGHLEADS_PASSWORD. Preview URLs use `/p/business-name-id?t=secret` on this one domain. No individual DNS records are needed. Configure proxy login throttling before production use.

This release is not deployed or live-tested on Mark's NAS. Docker image build, actual folder ACLs, Dockge path mapping and NPM networking still require verification there. It is a single-owner foundation; SMS/email delivery, AI site generation and invoicing integrations are not implemented yet.

## Daily use

Search a trade and town, wait for Apify to finish, then press Check results. Review a small shortlist. No website listed means no website was returned by that source; search separately before concluding the business has none. A missing email stays missing; the app never invents one.

Open a lead, check the business details, add confirmed services and preview wording, then enable the share link. The public page is a clearly labelled proposal and makes no invented claims about credentials, reviews or experience. All three themes currently share a one-page layout; custom industry layouts, photography and full page editing come later. A list of public services does not establish permission to copy another website's text or photos.

Read and personalise the outreach draft. Record actual contact manually and set the follow-up date. Use Do not contact to retain an objection in your suppression list. This build does not send anything or infer marketing permission from a public phone number.

## Costs and practical limits

The app has no software subscription. TrueNAS power, storage and backups remain your costs. Lead data and future AI/SMS services are external services, rather than processes running on TrueNAS.

Apify's Free plan currently advertises $5 of usage. For compass/crawler-google-places, the live free-tier pricing checked on 23 November 2026 was $0.004 per place plus a small start fee; 25 basic places is approximately $0.10 before any other charge. This is not a guaranteed quote. Filters, contacts and additional data cost extra. The app requests maxTotalChargeUsd=0.25, but you must also configure account-level limits and check actual charges in Apify. There is no monthly app budget controller yet. No paid run was executed during development.

Google Maps data is not a list of qualified buyers. Small targeted batches and individual review matter more than collecting thousands of names. Focus first on garages, kitchen firms and builders in Manchester/Lancashire, where Mark already has relevant examples.

Sources checked:
- https://apify.com/pricing
- https://apify.com/compass/crawler-google-places/pricing
- https://docs.apify.com/api/v2/actors-runs-post
- https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/
- https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/electronic-and-telephone-marketing/electronic-mail-marketing/

UK outreach needs a distinction between corporate subscribers and sole traders/some partnerships. Publicly listed contact details do not by themselves permit marketing email or SMS. Sole traders normally need consent unless the limited existing-customer exception applies. Corporate messages still need clear sender identity, an opt-out route and any applicable data protection obligations. Build this distinction and suppression checks into delivery before enabling messaging.

## Backup and recovery

The database is `/mnt/apps/highleads/data/ivory.sqlite3` on TrueNAS (mounted at `/data` inside the container). Generated HTML snapshots are in `/mnt/photographers_data/highleadclients/<business-slug>/index.html`. Back up both datasets. The database remains authoritative for business details, preview enablement, tokens and expiry; the HTML files alone do not restore the CRM. Keep both directories on upgrades. For a consistent live backup use SQLite's backup API, or stop the app while taking a volume/dataset backup. Do not copy only the main database while it is live in WAL mode. Retain the compose configuration and secrets securely as well. Restore-test a backup before relying on this for live customer records. App-secret changes invalidate form tokens; password changes take effect after restart.

If an Apify start request times out, its outcome is marked UNCERTAIN and new searches are blocked to avoid duplicate charges. Inspect the run in Apify before an operator resolves the database search record. Recovery through the dashboard is a planned improvement.

## Next implementation stages

1. Deploy and verify this foundation on the actual TrueNAS/NPM network. Add proper session login, login throttling, searchable activity history, search-run recovery and tested backups.
2. Add differentiated industry layouts, image selection/upload and an editor. Integrate AI generation with configurable spend limits and structured business facts. API usage is separate from a ChatGPT subscription; local AI is an alternative subject to hardware testing.
3. Connect business email and SMS, with provider credentials, permission records, suppression enforcement, opt-out handling, message approval and delivery webhooks. No bulk prospect messaging should be switched on by default.
4. Connect existing Ivory Digital quotes/invoices using its actual API. Preserve one authoritative set of financial records. Track setup fees separately from recurring revenue.
5. Add website audit checks and an explainable opportunity score, qualified lead conversion and revenue reporting.
6. Add business isolation, roles, billing and onboarding only when preparing to sell access. The current version is single-owner and should not be sold as multi-tenant software.

## Verification

Run `pip install -r requirements-dev.txt` and `python -m unittest discover -s tests -v` in a development environment. Tests cover dashboard authentication, CSRF, imports, suppression state, draft visibility, share tokens, expiry, escaped prospect content and mocked provider integration. All seven automated tests passed locally. These do not verify a real Apify account, Docker image build, TrueNAS deployment or SMS/email delivery. Browser rendering checks were attempted but could not run because this environment denied Chromium the sockets it needs. Desktop/mobile visual review is still required on deployment.
