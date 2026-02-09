# Setting up subdomains for afta.systems

We need two subdomains pointing to our demo apps. Each one is just a single DNS record — should take about 5 minutes total.

## What to do

1. Log into the registrar where `afta.systems` is managed
2. Find the DNS settings (might be called "DNS Records", "Zone Editor", "DNS Management" — depends on the registrar)
3. Add these two records:

### Record 1: booktrailers.afta.systems

- **Type:** CNAME
- **Host / Name:** `booktrailers`
- **Value / Target:** `book-trailer-345011742806.us-central1.run.app`
- **TTL:** leave default

### Record 2: linkedin.afta.systems

- **Type:** CNAME
- **Host / Name:** `linkedin`
- **Value / Target:** `auto-marketing-345011742806.us-central1.run.app`
- **TTL:** leave default

4. Save both records

That's it from your side. No certificates or IP addresses needed — SSL is handled automatically on Google's end once Dima connects the domains to the services.

## Notes

- Changes might take a few minutes to propagate (sometimes up to an hour, but usually fast)
- If we need more subdomains later, same process — just another CNAME record each time
