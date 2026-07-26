# Lead Research Playbook

Use this when you want cleaner leads than fully automated dork scraping. The goal is to move fast manually while keeping bad pages out of the CSV.

## Capture Fields

For every saved lead, capture:

- `segment`
- `business_name`
- `owner_or_founder_name`
- `website`
- `email`
- `phone`
- `linkedin`
- `instagram`
- `youtube_or_x`
- `booking_url`
- `source_query`
- `source_url`
- `website_quality_notes`
- `why_relevant`
- `offer_angle`
- `status`

Recommended statuses:

- `new`
- `qualified`
- `needs_manual_research`
- `rejected`
- `contacted`

## Dork 1: Agency Owners

```text
("agency owner" OR "founder") ("marketing agency" OR "branding agency" OR "creative agency") ("contact" OR "email") ("United States" OR "United Kingdom" OR "Canada" OR "Germany")
```

Finds agency owners with websites/contact pages where you can collect email, LinkedIn, and Instagram.

### How To Use

1. Paste the dork into Google.
2. Open agency websites only, not random blog posts, podcasts, directories, or social pages.
3. Check homepage, About, Contact, footer, and team/founder pages.
4. Capture agency name, founder/owner name, website, email, LinkedIn, Instagram.
5. Check website quality: outdated design, weak portfolio, poor CTA, slow loading, bad mobile layout.
6. Save only active agencies that could use better design/dev support or white-label fulfillment.

### Refinements

```text
"SEO agency" "founder"
"small business marketing agency" "contact"
"creative agency" "Instagram" "LinkedIn"
("creative agency" OR "branding studio") ("Webflow" OR "WordPress" OR "Shopify") ("contact" OR "new business")
```

### Directory Suggestion

Clutch, but only use it to discover company names/domains. Do not save directory pages as leads.

### Qualification Checklist

- Has real clients, case studies, portfolio, or testimonials.
- Founder/owner is visible on site or LinkedIn.
- Agency looks active.
- Website has a clear improvement opportunity, or they may need white-label web support.

### Red Flags

- Big agency with large internal dev/design team.
- No real portfolio.
- No owner/founder name.
- No active social links.
- Directory/listicle/podcast/video result instead of company website.

### Offer Angle

Do not pitch “you need a website” to agency owners. Pitch:

```text
White-label Webflow, WordPress, Shopify, or landing page fulfillment for overflow client projects.
```

## Dork 2: Coaches And Consultants

```text
("business coach" OR "fitness coach" OR "life coach" OR "consultant") ("book a call" OR "apply now") ("email" OR "contact") ("USA" OR "UK" OR "Europe")
```

Finds coaches and consultants with paid offers who may need better landing pages or funnels.

### How To Use

1. Open personal brand or coaching websites.
2. Look for offer signals: book a call, apply now, program, masterclass, coaching.
3. Capture email, LinkedIn, Instagram, website, and booking link.
4. Check if the site looks basic, confusing, template-like, or not premium.
5. Save only coaches who look active and monetized.

### Refinements

```text
"high ticket coach" "book a call"
"business consultant" "apply now" "LinkedIn"
"online coach" "Instagram" "contact"
```

### Directory Suggestion

LinkedIn, used only to verify the person is active and credible.

### Qualification Checklist

- Has a clear paid offer or coaching program.
- Has testimonials, content, audience, or booking page.
- Website quality does not match offer quality.

### Red Flags

- No clear offer or monetization.
- No recent content or social activity.
- No booking/contact path.

### Offer Angle

```text
High-converting landing page, booking funnel, or premium personal-brand website.
```

## Dork 3: Creators

```text
("creator" OR "YouTuber" OR "newsletter") ("course" OR "community" OR "sponsorship") ("business inquiries" OR "contact") ("United States" OR "Canada" OR "UK")
```

Finds creators who make money from courses, sponsorships, newsletters, or communities.

### How To Use

1. Open creator websites, media kits, newsletter pages, or personal brand sites.
2. Look for monetization: course, paid community, sponsorships, consulting, digital products.
3. Capture business email, website, Instagram, LinkedIn, YouTube/X if available.
4. Check if their site is missing key pages: media kit, course page, sponsor page, booking page.
5. Save only creators with active content and a clear business model.

### Refinements

```text
"business inquiries" "course creator"
"newsletter creator" "sponsorship"
"YouTuber" "media kit" "email"
```

### Directory Suggestion

YouTube, used to verify activity and audience. Save the creator website or media kit as the lead URL, not the YouTube video.

### Qualification Checklist

- Has an active audience.
- Has monetization beyond free content.
- Website/personal brand looks weaker than content quality.

### Red Flags

- No contact method.
- Small inactive creator with no paid offer.
- Only a video/social result and no business site.

### Offer Angle

```text
Media kit, sponsor page, course page, paid community landing page, or creator personal-brand site.
```

## Dork 4: Premium Small Businesses

```text
("salon" OR "clinic" OR "fitness studio" OR "interior designer") ("book online" OR "contact us") ("email" OR "Instagram") ("New York" OR "London" OR "Paris" OR "Toronto")
```

Finds premium small businesses with booking/contact websites.

### How To Use

1. Open local business websites.
2. Check if they have premium services, strong reviews, nice photos, or active Instagram.
3. Capture business name, owner if visible, email, Instagram, LinkedIn if available, website.
4. Look for website problems: outdated design, PDF menu/services, poor mobile layout, hidden booking button.
5. Save only businesses that look like they can afford a $2k+ revamp.

### Refinements

```text
"luxury salon" "book online"
"aesthetic clinic" "Instagram" "contact"
"interior designer" "portfolio" "email"
```

### Directory Suggestion

Google Maps or local directories, used only to find real business websites.

### Qualification Checklist

- Premium positioning or high-ticket service.
- Active Instagram or strong visuals.
- Booking/contact path exists but could be improved.
- Looks able to afford a $2k+ website/funnel revamp.

### Red Flags

- Low-price commodity business.
- No active web/social presence.
- No clear service, booking, or contact path.

### Offer Angle

```text
Premium website revamp, better booking flow, mobile-first service pages, conversion-focused local landing page.
```

## Universal Rejection Rules

Reject these unless they point to an actual company website:

- YouTube videos
- Apple/Spotify podcast pages
- LinkedIn profiles as primary lead URL
- Facebook/Instagram-only profiles
- Reddit threads
- ZoomInfo/RocketReach profiles
- Email list sellers
- “Top 10 agency” listicles
- Clutch or directory pages as final lead URLs
- PDFs, spreadsheets, or download files

## Outreach Timing

Do not send emails immediately after discovery. First qualify the lead and write a reason:

```text
why_relevant: Agency offers branding but no visible web build partner.
offer_angle: White-label Webflow/WordPress fulfillment.
personalization_line: Saw your branding work for local service businesses; curious if you ever need overflow web build support.
```

Only send when `why_relevant`, `offer_angle`, and contact info are present.
