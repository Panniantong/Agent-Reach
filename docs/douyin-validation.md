# Douyin Validation Notes

This file records real-world validation of the built-in Douyin script workflow in this fork.

## Scope validated

Validated against real share-text inputs copied from the Douyin app, not just clean URLs.

The following command groups were tested:

- `--action info`
- `--action download`
- `--action extract`

## Validation summary

### Case 1: Traffic / ambient-audio style video

Input was a real Douyin share text for a traffic-related clip.

Observed behavior:

- `info` succeeded
- `download` succeeded
- `extract` completed end-to-end
- transcript text was empty

Conclusion:

- The processing pipeline works end-to-end.
- Empty transcript does not necessarily mean the script failed.
- Likely causes: little or no clear speech, mostly ambient sound/BGM, or no useful speech recognized by the model.

This case motivated the `warning` field for empty transcript results.

### Case 2: Spoken promotional food video

Input was a real Douyin share text for a spoken promotional clip about a seafood buffet.

Observed behavior:

- `info` succeeded
- `download` succeeded
- `extract` succeeded
- transcript text was returned successfully

Conclusion:

- Real-world transcript extraction works when the source audio has clear speech.
- The current built-in script workflow is viable as a link-first MVP for Douyin.

## Current capability boundary

This fork currently supports:

- Parse Douyin share links
- Download watermark-free video files
- Extract transcript text from downloaded video audio

This fork does **not** yet provide built-in Douyin search.

## Recommended operator guidance

- Use `info` first when testing a new link pattern.
- Treat empty transcript as a warning, not a fatal error.
- Prefer videos with clear spoken audio when validating transcript quality.
- Keep transcript quality expectations realistic; recognition quality depends on the source audio and the speech model.
