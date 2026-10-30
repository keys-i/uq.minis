# Connect Buzzy

Rubric events and the UQU club directory work without an account
Open Clubby’s noticeboard or Planny’s Buzzy view, then follow clubs or save individual events
Public announcements are loaded automatically from an hourly backend snapshot
The union directory covers all listed clubs and retains their available social links
Public event banners and club logos come from Rubric's `resources.hellorubric.com` and `resources.getqpay.com` image hosts
The browser loads those images lazily and keeps cards usable when an image cannot load
A directory listing does not authorise access to that club's social account; each account owner must grant the relevant API access

## Discord

Create an application at the [Discord developer portal](https://discord.com/developers/applications), add its bot and invite it only to servers where an administrator authorises the access
Use the portal's bot installation flow and the minimum permissions needed to view those servers' scheduled events
This integration does not need administrator permissions, message-content access or a persistent gateway connection

Store the new bot token in `backend/.minis/clubby/.env` with this shape, or provide `DISCORD_BOT_TOKEN` in the backend process environment

```dotenv
DISCORD_BOT_TOKEN=your_new_bot_token
```

Keep that file private, outside Git, and restrict its permissions to your user account
On macOS/Linux, run `chmod 600 .minis/clubby/.env` from `backend/`
Enable Developer Mode in Discord and copy the authorised server IDs
In Buzzy, choose **Announcement tools → Connect club accounts**, enter those comma-separated IDs and refresh the scheduled events
The token stays in Python and never enters the React page or exported calendar

The CLI offers the same read workflow

```sh
uv run mini clubby events --guild SERVER_ID -o events.csv
```

Saved Discord scheduled-event API arrays can also be imported through Buzzy's **Announcement tools → Import announcements** dialog
An event cancelled by its organiser is retained as cancelled; a complete refresh removes disappeared events from the selected servers only
Recurring series retain the occurrence returned by Discord rather than expanding future instances

The historical `agg-soc` prototype contained an exposed token
Its literal has been removed from the working source, but its owner must reset it in Discord because repository history may retain it

## Instagram and Facebook

The backend can read recent Facebook Page posts and professional Instagram media through approved Meta access
The Instagram reader uses the Instagram API with Facebook Login, with the professional account linked to a Page the authorising person manages
Personal Instagram accounts and Instagram Login tokens are not supported by this reader
Follow the [Instagram platform](https://developers.facebook.com/docs/instagram-platform/) and [Pages API](https://developers.facebook.com/docs/pages-api/) setup and access-review requirements for the chosen product
For Facebook, obtain a Page access token with approved Page read access
For Instagram, obtain the Facebook Login access token and approved Instagram read access for the linked professional account
Exact permissions depend on the account and app; validate them in the app dashboard before requesting access, and request read permissions rather than posting permissions for these readers
An ordinary student login does not grant read access to every club's social feed

## LinkedIn

Organisation posts require an organisation role and approved API access
Follow [LinkedIn Community Management access](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview)
The reader uses the [Posts API's author finder](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api) and requires approved `r_organization_social` access for the organisation
Member feeds and posting actions are outside this reader

## Configure approved social readers

Once an account owner authorises access, store the relevant settings in `backend/.minis/clubby/.env` or the backend process environment
Replace the example placeholders with the owner's approved token and API versions currently supported by the provider
Meta versions use `vNN.N`; LinkedIn versions use `YYYYMM`

```dotenv
META_API_VERSION=vNN.N
FACEBOOK_ACCESS_TOKEN=your_approved_page_read_token
INSTAGRAM_ACCESS_TOKEN=your_approved_facebook_login_read_token
LINKEDIN_VERSION=YYYYMM
LINKEDIN_ACCESS_TOKEN=your_approved_organisation_read_token
```

Only configure the providers you use, and keep the file private with `chmod 600 .minis/clubby/.env` from `backend/`
Tokens stay in the backend, travel in API authorisation headers and are excluded from exports
The environment takes precedence over the saved file, including when a credential is empty or invalid

In Buzzy, open **Announcement tools → Connect club accounts**, choose the provider and enter its numeric Page, Instagram account or LinkedIn organisation ID
Add the club name and its exact union directory link to match announcements with clubs you follow, then choose **Refresh social announcements**
The standalone Clubby browser form also offers **Read authorised social announcements** as a JSON download
The equivalent CLI command is

```sh
uv run mini clubby posts --provider instagram --account ACCOUNT_ID \
  --club "Your club" -o outputs/posts.json
```

Use `facebook` or `linkedin` for the other providers
The CLI JSON imports directly through Buzzy's **Announcement tools → Import announcements** dialog
Each refresh reads one recent API page of at most 100 posts, with an 8 MiB response limit and a 30-second network inactivity timeout
This is a recent-post window, not a complete historical export; older saved posts remain when absent from a refresh
Original URLs give imports stable identities, so repeated reads update posts while retaining calendar selections and known union links
Read failures, revoked access, invalid responses and rate limits preserve existing plan data and exports

Publication dates are not event dates
Undated posts remain searchable; to plan an event, save an announcement with the exact event time and useful details reviewed from the original source
The readers do not poll automatically, refresh tokens, register developer apps or obtain club consent on your behalf
Until access is approved, use an authorised export or save the original post link and details

## Social import format

Buzzy accepts a JSON array, with an original URL and title on every record
Omit event times for ordinary posts; event times must include a time zone
Source details stay editable and imports update the same original URL instead of duplicating it

```json
[
  {
    "title": "Board games evening",
    "source": "Instagram",
    "club": "Your club",
    "url": "https://www.instagram.com/p/POST_ID/",
    "start": "2026-10-25T18:00:00+10:00",
    "end": "2026-10-25T21:00:00+10:00",
    "notes": "Location, cost, registration link and what to bring"
  }
]
```

## Calendar subscriptions

Calendy exposes `http://127.0.0.1:8765/calendar.ics` while minis runs
Choose a device calendar in Calendy, or copy the live feed address into another app's **Subscribe from URL** control
Calendy also offers Google and Outlook subscription links when the feed has a securely hosted address
Cloud calendar providers cannot fetch your computer's loopback address
Cross-device subscriptions require a hosted service with authentication; do not expose this local development server publicly
