# Avatar refinement

Created using the built-in imagegen tool from `images/profile.jpg`. The original
photograph is retained. `images/profile-refined.png` is the full-resolution result;
`images/profile-refined.webp` is the 512 × 512 homepage asset.

The second revision removes the backpack straps and softens clothing wrinkles.
Its full-resolution image is `images/profile-refined-v2.png`, with a web copy at
`images/profile-refined-v2.webp`. This is an alternate draft. The user preferred
the first refined version, so the homepage uses `images/profile-refined.webp`.

## Initial edit prompt

Use case: identity-preserve.
Asset type: a natural professional avatar photograph for the subject's academic homepage, displayed in a small circular crop.
Input image: /Users/zzzzchs/Local/hhf/ZzZZCHS.github.io/images/profile.jpg is the EDIT TARGET, not merely an inspiration image.
Edit this actual photograph conservatively. Preserve the person's identity exactly: unchanged facial structure, eye shape and spacing, nose, mouth, ears, jaw, hairstyle, age, natural skin tone, and the same gentle closed-mouth smile and front-facing pose. Preserve realistic skin texture and the existing blue heather T-shirt; keep backpack straps where they remain in the crop. Do not beautify, reshape, whiten teeth or skin, replace clothing, remove facial hair, or invent facial details.
Refinements: subtly lift exposure on the face and eyes, balance white balance, keep pleasant natural daylight and soft contrast, lightly improve photographic clarity without over-sharpening or airbrushing. Remove distracting background passersby and soften the existing green trees and brick campus buildings with realistic optical background blur. Keep the original outdoor campus setting recognizable; do not substitute a studio or a different location.
Composition: square high-resolution head-and-shoulders crop suitable for a circle. Center the face horizontally, show the full hairstyle with comfortable headroom and both shoulders, position eyes around the upper two-fifths of the square. The head including hair should occupy approximately half of the image height, with the lower crop around the upper chest. No circular mask baked in, no border, text, graphics, watermark, glamor filters, or artificial skin. The result must look like a carefully retouched version of the same photo, not a newly invented portrait.
## Clothing refinement prompt

Use case: precise-object-edit, identity-preserve.
Edit target: the provided refined avatar photograph at /Users/zzzzchs/Local/hhf/ZzZZCHS.github.io/images/profile-refined.png.
Make ONLY the following clothing edits:
1. Completely remove both black backpack shoulder straps, the visible black strap/bag edges near the sides of the torso, and the little backpack logo label. Reconstruct the blue heather cotton T-shirt underneath them naturally, matching the exact existing shirt color, knit texture, seams, body fit, shoulder outline, and lighting.
2. Gently reduce the shirt's noticeable creases, especially across the shoulders and chest. Retain realistic cotton heather texture, neckline and stitching, and a few natural folds so it looks like a neatly worn real T-shirt, not a perfectly flat or plastic surface. Do not change the clothing type, neckline, color, or sleeve length.
Strict invariants: preserve the exact face and identity, hair, facial features and geometry, skin texture, subtle facial hair, expression, gaze, neck, body proportions, pose, framing, exposure, colors, and blurred campus background of this input. Do not retouch or redraw the face. Do not add objects, text, branding, accessories, a jacket or a different shirt. Keep the same square composition and resolution. Photorealistic, minimal local retouching confined to the shirt and backpack straps.
