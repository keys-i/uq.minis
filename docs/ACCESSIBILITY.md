# Accessibility

UQ minis should work for students using keyboards, assistive technology, small screens or reduced motion
WCAG 2.2 level AA is the browser interface's design target, not a claim of audited conformance
No complete independent accessibility audit or screen-reader compatibility matrix has been completed

## Browser support in the implementation

- A skip link leads to the main tools, with labelled navigation and semantic headings
- Forms use visible labels, native controls and visible keyboard focus
- Dialogues use the browser's modal dialogue element, an accessible title, a close button and Escape handling
- Errors and save feedback use alert or status regions
- Assessment and marks information includes text and tables, alongside the calendar and Gantt views
- Official deadlines and personal targets have text labels as well as colours
- Layouts adapt to narrower screens; calendars and wide tables can scroll horizontally
- Card titles provide the main card link, with separate Follow and Save buttons rather than nested interactive controls
- Event banners and club logos load lazily, reserve their layout space and fall back to initials when unavailable
- Clubs without an event banner use their own logo as the cover, and upcoming-event details come from the saved public feed
- Source names remain in event-link accessible labels and filters without adding another visible link to the same destination
- Nudgy previews a personal target as its slider moves while retaining the official deadline
- Animal motion respects reduced-motion preferences and the footer’s Accessibility & sound → Still wildlife setting, with off-screen and hidden-tab animation suspended
- Species badges have accessible status names, and each independent pat button announces its animal's reaction without relying on animation
- Hover and keyboard focus select mini previews; the full explanation is available to assistive technology while the visual typing effect runs
- My story opens a labelled native popover with a close button, Escape dismissal, written location, conservation context and source link
- Flags and regional palettes accompany written locations rather than replacing them
- Flags and range maps use local SVG artwork instead of operating-system emoji; their movement respects still-wildlife and reduced-motion settings
- Visual calls work without sound; optional quiet recordings only play after a click and can be disabled
- Native accessibility settings keep focus inside the modal dialogue and return it when dismissed
- The desktop mini menu keeps its icon controls visible and expands labels on hover or keyboard focus, with a native menu button on small screens
- Form controls remain above decorative wildlife; animals settle while fields have focus and their routes respond to page resizing
- The footer provides a GitHub link, author credit and working controls for motion, contrast, reading size and optional sound
- Calendar choices provide live subscriptions for device calendars, Google, Outlook or another calendar app, with a copyable feed address
- Browser illustrations and the DynaPuff and Comic Neue font families are bundled locally, with no font-service or terminal-art requests at runtime

Use Tab and Shift+Tab to move between controls, Enter to activate buttons and links, and Space for checkboxes and buttons
Escape closes an open dialogue
Calendar cards and the assessment list open the same assessment details
The CLI and editable JSON/ICS exports provide alternatives for some workflows; they don't replace accessible browser behaviour

## Terminal options

Run a mini's `--help` command to find its direct commands without the interactive picker
`MINI_MOTION=0` keeps terminal artwork and captions still
`NO_COLOR=1` removes colour while keeping text and static artwork
Redirected input uses plain prompts, and `mini --no-input` shows command help instead of opening the root picker
Not every mini has the same headless editing commands; Planny uses editable JSON imports for enrolments and assessments
Screen-reader behaviour varies with the terminal and has not been comprehensively tested

## Check interface changes

Exercise the actual changed workflow with invented data, including empty, loading, saved and error states

1. Complete it using only the keyboard, checking focus order, visible focus and dialogue focus return
2. Read labels, headings, errors, save feedback and tables with a screen reader, such as VoiceOver or NVDA
3. Check 200% and 400% browser zoom and a narrow viewport around 320 CSS pixels, including access to horizontally scrolling content
4. Check long course names, assessment instructions, dates, marks and source links without clipped controls
5. Check pointer and touch targets, reduced motion, forced colours and text/background contrast across the affected habitat palettes
6. Confirm that colours, animal reactions, dragging or hover are never the only way to understand or perform an action

Automated tests and a successful build cannot establish that these checks pass
State the browser, operating system, assistive technology and checks exercised in the pull request

## Known assessment gaps

Full keyboard and screen-reader coverage, forced-colour rendering, touch behaviour and high-zoom layouts still need systematic assessment
Native date/time controls and modal dialogues can behave differently across browser and assistive-technology combinations
This document records existing implementation support and testing expectations without treating untested combinations as verified

## Report a barrier

Use the [bug report form](https://github.com/keys-i/uq.minis/issues/new?template=bug.yml) and describe the task you couldn't complete
Include the mini, browser or terminal, operating system, assistive technology and input method when relevant
You don't need to disclose a disability or medical information
Remove real marks, student identifiers, private announcements and credentials from examples
For a private report, use the contact guidance in the [code of conduct](../.github/CODE_OF_CONDUCT.md#report-a-concern)
