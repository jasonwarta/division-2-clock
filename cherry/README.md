# Cherry-picked frames for OCR validation

Extracted from `Screen Recording 2026-04-30 124356.mp4` using bbox `71,38,66,35` and 4x nearest-neighbor upscale.

| File | video_ms | Claude's read | Notes |
|---|---|---|---|
| A.png | 0 | 05:51 | first frame, clean |
| B.png | 30000 | 06:01 | OCR misread as 00:01 originally |
| C.png | 50000 | 06:07 | OCR misread as 00:07 originally |
| D.png | 3030000 | **20:03 ?** | last digit partially clipped on right edge |
| E.png | 3050000 | 20:10 | clean |
| F.png | 3055000 | **20:11 or 20:12 ?** | ambiguous trailing digit |
| G.png | 3070000 | 20:17 | clean |
| H.png | 5800000 | 12:23 | clean |
| I.png | 5820000 | **12:32 ?** | last digit unclear |
| J.png | 8000000 | 01:17 | clean |
| K.png | 8500000 | **04:58 ?** | last digit partially clipped |
| L.png | 9020000 | 07:29 | clean |

The right-edge clip on D, I, K suggests the bbox should extend a few pixels further right.
